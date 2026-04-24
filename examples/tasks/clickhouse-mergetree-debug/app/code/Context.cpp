#include <map>
#include <set>
#include <optional>
#include <memory>
#include <Poco/Mutex.h>
#include <Poco/UUID.h>
#include <Poco/Net/IPAddress.h>
#include <Poco/Util/Application.h>
#include <Common/Macros.h>
#include <Common/escapeForFileName.h>
#include <Common/setThreadName.h>
#include <Common/Stopwatch.h>
#include <Common/formatReadable.h>
#include <Common/Throttler.h>
#include <Common/thread_local_rng.h>
#include <Coordination/KeeperStorageDispatcher.h>
#include <Compression/ICompressionCodec.h>
#include <Core/BackgroundSchedulePool.h>
#include <Formats/FormatFactory.h>
#include <Processors/Formats/InputStreamFromInputFormat.h>
#include <Databases/IDatabase.h>
#include <Storages/IStorage.h>
#include <Storages/MarkCache.h>
#include <Storages/MergeTree/MergeList.h>
#include <Storages/MergeTree/ReplicatedFetchList.h>
#include <Storages/MergeTree/MergeTreeData.h>
#include <Storages/MergeTree/MergeTreeSettings.h>
#include <Storages/CompressionCodecSelector.h>
#include <Storages/StorageS3Settings.h>
#include <Disks/DiskLocal.h>
#include <TableFunctions/TableFunctionFactory.h>
#include <Interpreters/ActionLocksManager.h>
#include <Interpreters/ExternalLoaderXMLConfigRepository.h>
#include <Core/Settings.h>
#include <Core/SettingsQuirks.h>
#include <Access/AccessControlManager.h>
#include <Access/ContextAccess.h>
#include <Access/EnabledRolesInfo.h>
#include <Access/EnabledRowPolicies.h>
#include <Access/QuotaUsage.h>
#include <Access/User.h>
#include <Access/Credentials.h>
#include <Access/SettingsProfile.h>
#include <Access/SettingsConstraints.h>
#include <Access/ExternalAuthenticators.h>
#include <Access/GSSAcceptor.h>
#include <Interpreters/ExpressionJIT.h>
#include <Dictionaries/Embedded/GeoDictionariesLoader.h>
#include <Interpreters/EmbeddedDictionaries.h>
#include <Interpreters/ExternalDictionariesLoader.h>
#include <Interpreters/ExternalModelsLoader.h>
#include <Interpreters/ExpressionActions.h>
#include <Interpreters/ProcessList.h>
#include <Interpreters/InterserverCredentials.h>
#include <Interpreters/Cluster.h>
#include <Interpreters/InterserverIOHandler.h>
#include <Interpreters/SystemLog.h>
#include <Interpreters/Context.h>
#include <Interpreters/DDLWorker.h>
#include <Interpreters/DDLTask.h>
#include <Interpreters/MVCCWorker.h>
#include <IO/ReadBufferFromFile.h>
#include <IO/UncompressedCache.h>
#include <IO/MMappedFileCache.h>
#include <Parsers/ASTCreateQuery.h>
#include <Parsers/ParserCreateQuery.h>
#include <Parsers/parseQuery.h>
#include <Common/StackTrace.h>
#include <Common/Config/ConfigProcessor.h>
#include <Common/Config/AbstractConfigurationComparison.h>
#include <Common/ZooKeeper/ZooKeeper.h>
#include <Common/ShellCommand.h>
#include <Common/TraceCollector.h>
#include <common/logger_useful.h>
#include <Common/RemoteHostFilter.h>
#include <Interpreters/DatabaseCatalog.h>
#include <Storages/MergeTree/BackgroundJobsExecutor.h>
#include <Storages/MergeTree/MergeTreeDataPartUUID.h>
#include <Storages/StorageExplicitDistributed.h>
#include <Storages/MergeTree/MergeTreeMetadataCache.h>
#include <Common/getNumberOfPhysicalCPUCores.h>

#if USE_ROCKSDB
#include <rocksdb/table.h>
#endif

namespace ProfileEvents
{
    extern const Event ContextLock;
    extern const Event CompiledCacheSizeBytes;
}

namespace CurrentMetrics
{
    extern const Metric ContextLockWait;
    extern const Metric BackgroundMovePoolTask;
    extern const Metric BackgroundSchedulePoolTask;
    extern const Metric BackgroundBufferFlushSchedulePoolTask;
    extern const Metric BackgroundDistributedSchedulePoolTask;
    extern const Metric BackgroundMessageBrokerSchedulePoolTask;
}


namespace DB
{

namespace ErrorCodes
{
    extern const int BAD_ARGUMENTS;
    extern const int BAD_GET;
    extern const int UNKNOWN_DATABASE;
    extern const int UNKNOWN_TABLE;
    extern const int TABLE_ALREADY_EXISTS;
    extern const int THERE_IS_NO_SESSION;
    extern const int THERE_IS_NO_QUERY;
    extern const int NO_ELEMENTS_IN_CONFIG;
    extern const int TABLE_SIZE_EXCEEDS_MAX_DROP_SIZE_LIMIT;
    extern const int SESSION_NOT_FOUND;
    extern const int SESSION_IS_LOCKED;
    extern const int LOGICAL_ERROR;
    extern const int NOT_IMPLEMENTED;
}


class NamedSessions
{
public:
    using Key = NamedSessionKey;

    ~NamedSessions()
    {
        try
        {
            {
                std::lock_guard lock{mutex};
                quit = true;
            }

            cond.notify_one();
            thread.join();
        }
        catch (...)
        {
            tryLogCurrentException(__PRETTY_FUNCTION__);
        }
    }

    /// Find existing session or create a new.
    std::shared_ptr<NamedSession> acquireSession(
        const String & session_id,
        ContextPtr context,
        std::chrono::steady_clock::duration timeout,
        bool throw_if_not_found)
    {
        std::unique_lock lock(mutex);

        auto & user_name = context->client_info.current_user;

        if (user_name.empty())
            throw Exception("Empty user name.", ErrorCodes::LOGICAL_ERROR);

        Key key(user_name, session_id);

        auto it = sessions.find(key);
        if (it == sessions.end())
        {
            if (throw_if_not_found)
                throw Exception("Session not found.", ErrorCodes::SESSION_NOT_FOUND);

            /// Create a new session from current context.
            it = sessions.insert(std::make_pair(key, std::make_shared<NamedSession>(key, context, timeout, *this))).first;
        }
        else if (it->second->key.first != context->client_info.current_user)
        {
            throw Exception("Session belongs to a different user", ErrorCodes::SESSION_IS_LOCKED);
        }

        /// Use existing session.
        const auto & session = it->second;

        if (!session.unique())
            throw Exception("Session is locked by a concurrent client.", ErrorCodes::SESSION_IS_LOCKED);

        session->context->client_info = context->client_info;

        return session;
    }

    void releaseSession(NamedSession & session)
    {
        std::unique_lock lock(mutex);
        scheduleCloseSession(session, lock);
    }

private:
    class SessionKeyHash
    {
    public:
        size_t operator()(const Key & key) const
        {
            SipHash hash;
            hash.update(key.first);
            hash.update(key.second);
            return hash.get64();
        }
    };

    /// TODO it's very complicated. Make simple std::map with time_t or boost::multi_index.
    using Container = std::unordered_map<Key, std::shared_ptr<NamedSession>, SessionKeyHash>;
    using CloseTimes = std::deque<std::vector<Key>>;
    Container sessions;
    CloseTimes close_times;
    std::chrono::steady_clock::duration close_interval = std::chrono::seconds(1);
    std::chrono::steady_clock::time_point close_cycle_time = std::chrono::steady_clock::now();
    UInt64 close_cycle = 0;

    void scheduleCloseSession(NamedSession & session, std::unique_lock<std::mutex> &)
    {
        /// Push it on a queue of sessions to close, on a position corresponding to the timeout.
        /// (timeout is measured from current moment of time)

        const UInt64 close_index = session.timeout / close_interval + 1;
        const auto new_close_cycle = close_cycle + close_index;

        if (session.close_cycle != new_close_cycle)
        {
            session.close_cycle = new_close_cycle;
            if (close_times.size() < close_index + 1)
                close_times.resize(close_index + 1);
            close_times[close_index].emplace_back(session.key);
        }
    }

    void cleanThread()
    {
        setThreadName("SessionCleaner");
        std::unique_lock lock{mutex};

        while (true)
        {
            auto interval = closeSessions(lock);

            if (cond.wait_for(lock, interval, [this]() -> bool { return quit; }))
                break;
        }
    }

    /// Close sessions, that has been expired. Returns how long to wait for next session to be expired, if no new sessions will be added.
    std::chrono::steady_clock::duration closeSessions(std::unique_lock<std::mutex> & lock)
    {
        const auto now = std::chrono::steady_clock::now();

        /// The time to close the next session did not come
        if (now < close_cycle_time)
            return close_cycle_time - now;  /// Will sleep until it comes.

        const auto current_cycle = close_cycle;

        ++close_cycle;
        close_cycle_time = now + close_interval;

        if (close_times.empty())
            return close_interval;

        auto & sessions_to_close = close_times.front();

        for (const auto & key : sessions_to_close)
        {
            const auto session = sessions.find(key);

            if (session != sessions.end() && session->second->close_cycle <= current_cycle)
            {
                if (!session->second.unique())
                {
                    /// Skip but move it to close on the next cycle.
                    session->second->timeout = std::chrono::steady_clock::duration{0};
                    scheduleCloseSession(*session->second, lock);
                }
                else
                    sessions.erase(session);
    current_roles.clear();
    use_default_roles = true;

    setSettings(*access->getDefaultSettings());
}

void Context::setUser(const Poco::Net::SocketAddress & address)
{
    auto lock = getLock();
    client_info.current_address = address;
    /// Find a user with such name and check the credentials.
//    auto new_user_id = getAccessControlManager().login(credentials, address.host());
    auto new_access = getAccessControlManager().getContextAccess(
        user_id.value(), /* current_roles = */ {}, /* use_default_roles = */ true,
        settings, current_database, client_info);

//    user_id = new_user_id;
    access = std::move(new_access);
    current_roles.clear();
    use_default_roles = true;

    setSettings(*access->getDefaultSettings());
}


void Context::setUser(const String & name, const String & password, const Poco::Net::SocketAddress & address)
{
    setUser(BasicCredentials(name, password), address);
}

void Context::setUserWithoutCheckingPassword(const String & name, const Poco::Net::SocketAddress & address)
{
    setUser(AlwaysAllowCredentials(name), address);
}

std::shared_ptr<const User> Context::getUser() const
{
    return getAccess()->getUser();
}

void Context::setQuotaKey(String quota_key_)
{
    auto lock = getLock();
    client_info.quota_key = std::move(quota_key_);
}

String Context::getUserName() const
{
    return getAccess()->getUserName();
}

std::optional<UUID> Context::getUserID() const
{
    auto lock = getLock();
    return user_id;
}


void Context::setCurrentRoles(const std::vector<UUID> & current_roles_)
{
    auto lock = getLock();
    if (current_roles == current_roles_ && !use_default_roles)
        return;
    current_roles = current_roles_;
    use_default_roles = false;
    calculateAccessRights();
}

void Context::setCurrentRolesDefault()
{
            query_factories_info.aggregate_functions.emplace(created_object);
            break;
        case QueryLogFactories::AggregateFunctionCombinator:
            query_factories_info.aggregate_function_combinators.emplace(created_object);
            break;
        case QueryLogFactories::Database:
            query_factories_info.database_engines.emplace(created_object);
            break;
        case QueryLogFactories::DataType:
            query_factories_info.data_type_families.emplace(created_object);
            break;
        case QueryLogFactories::Dictionary:
            query_factories_info.dictionaries.emplace(created_object);
            break;
        case QueryLogFactories::Format:
            query_factories_info.formats.emplace(created_object);
            break;
        case QueryLogFactories::Function:
            query_factories_info.functions.emplace(created_object);
            break;
        case QueryLogFactories::Storage:
            query_factories_info.storages.emplace(created_object);
            break;
        case QueryLogFactories::TableFunction:
            query_factories_info.table_functions.emplace(created_object);
    }
}


StoragePtr Context::executeTableFunction(const ASTPtr & table_expression)
{
    /// Slightly suboptimal.
    auto hash = table_expression->getTreeHash();
    String key = toString(hash.first) + '_' + toString(hash.second);

    StoragePtr & res = table_function_results[key];

    if (!res)
    {
        TableFunctionPtr table_function_ptr = TableFunctionFactory::instance().get(table_expression, shared_from_this());

        /// Run it and remember the result
        res = table_function_ptr->execute(table_expression, shared_from_this(), table_function_ptr->getName());
    }

    return res;
}


void Context::addViewSource(const StoragePtr & storage)
{
    if (view_source)
        throw Exception(
            "Temporary view source storage " + backQuoteIfNeed(view_source->getName()) + " already exists.", ErrorCodes::TABLE_ALREADY_EXISTS);
    view_source = storage;
}


StoragePtr Context::getViewSource()
{
    return view_source;
}

Settings Context::getSettings() const
{
    auto lock = getLock();
    return settings;
}


void Context::setSettings(const Settings & settings_)
{
    auto lock = getLock();
    auto old_readonly = settings.readonly;
    auto old_allow_ddl = settings.allow_ddl;
    auto old_allow_introspection_functions = settings.allow_introspection_functions;

    const auto old_settings = settings;

    settings = settings_;

    for(const auto setting : old_settings.all())
    {
        if(!settings.has(setting.getName()))
        {
            settings.setString(setting.getName(), setting.getValueString());
        }
    }

    if ((settings.readonly != old_readonly) || (settings.allow_ddl != old_allow_ddl) || (settings.allow_introspection_functions != old_allow_introspection_functions))
        calculateAccessRights();
}


void Context::setSetting(const StringRef & name, const String & value)
{
    auto lock = getLock();
    if (name == "profile")
    {
        setProfile(value);
        return;
    }
    settings.set(std::string_view{name}, value);

    if (name == "readonly" || name == "allow_ddl" || name == "allow_introspection_functions")
        calculateAccessRights();
}


void Context::setSetting(const StringRef & name, const Field & value)
{
    auto lock = getLock();
    if (name == "profile")
    {
        setProfile(value.safeGet<String>());
        return;
    }
    settings.set(std::string_view{name}, value);

    if (name == "readonly" || name == "allow_ddl" || name == "allow_introspection_functions")
        calculateAccessRights();
}


void Context::applySettingChange(const SettingChange & change)
{
    try
    {
        setSetting(change.name, change.value);
    }
    catch (Exception & e)
    {
        e.addMessage(fmt::format("in attempt to set the value of setting '{}' to {}",
                                 change.name, applyVisitor(FieldVisitorToString(), change.value)));
        throw;
    }
}


void Context::applySettingsChanges(const SettingsChanges & changes)

String Context::getDefaultFormat() const
{
    return default_format.empty() ? "TabSeparated" : default_format;
}


void Context::setDefaultFormat(const String & name)
{
    default_format = name;
}

MultiVersion<Macros>::Version Context::getMacros() const
{
    return shared->macros.get();
}

void Context::setMacros(std::unique_ptr<Macros> && macros)
{
    shared->macros.set(std::move(macros));
}

ContextPtr Context::getQueryContext() const
{
    auto ptr = query_context.lock();
    if (!ptr) throw Exception("There is no query or query context has expired", ErrorCodes::THERE_IS_NO_QUERY);
    return ptr;
}

bool Context::isInternalSubquery() const
{
    auto ptr = query_context.lock();
    return ptr && ptr.get() != this;
}

ContextPtr Context::getSessionContext() const
{
    auto ptr = session_context.lock();
    if (!ptr) throw Exception("There is no session or session context has expired", ErrorCodes::THERE_IS_NO_SESSION);
    return ptr;
}

ContextPtr Context::getGlobalContext() const
{
    auto ptr = global_context.lock();
    if (!ptr) throw Exception("There is no global context or global context has expired", ErrorCodes::LOGICAL_ERROR);
    return ptr;
}

ContextPtr Context::getBufferContext() const
{
    if (!buffer_context) throw Exception("There is no buffer context", ErrorCodes::LOGICAL_ERROR);
    return buffer_context;
}


const EmbeddedDictionaries & Context::getEmbeddedDictionaries() const
{
    return getEmbeddedDictionariesImpl(false);
}

EmbeddedDictionaries & Context::getEmbeddedDictionaries()
{
    return getEmbeddedDictionariesImpl(false);
}


const ExternalDictionariesLoader & Context::getExternalDictionariesLoader() const
{
    return const_cast<Context *>(this)->getExternalDictionariesLoader();
{
    std::lock_guard lock(shared->clusters_mutex);

    /// Do not update clusters if this part of config wasn't changed.
    if (shared->clusters && isSameConfiguration(*config, *shared->clusters_config, config_name))
        return;

    auto old_clusters_config = shared->clusters_config;
    shared->clusters_config = config;

    if (!shared->clusters)
        shared->clusters = std::make_unique<Clusters>(*shared->clusters_config, settings, config_name);
    else
        shared->clusters->updateClusters(*shared->clusters_config, settings, config_name, old_clusters_config);

    reloadExplicitDistributedTables(*shared->clusters);
}


void Context::setCluster(const String & cluster_name, const std::shared_ptr<Cluster> & cluster)
{
    std::lock_guard lock(shared->clusters_mutex);

    if (!shared->clusters)
        throw Exception("Clusters are not set", ErrorCodes::LOGICAL_ERROR);

    shared->clusters->setCluster(cluster_name, cluster);
}


void Context::initializeSystemLogs()
{
    auto lock = getLock();
    shared->system_logs = std::make_unique<SystemLogs>(getGlobalContext(), getConfigRef());
}

void Context::initializeTraceCollector()
{
    shared->initializeTraceCollector(getTraceLog());
}

#if USE_ROCKSDB
    void Context::initializeMergeTreeMetadataCache(const String & dir, MergeTreeMetadataCacheParams params, size_t delete_cache_fail_threshold)
    {
        shared->merge_tree_metadata_cache = MergeTreeMetadataCache::create(dir, params, delete_cache_fail_threshold, getGlobalContext());
    }
#endif

bool Context::hasTraceCollector() const
{
    return shared->hasTraceCollector();
}


std::shared_ptr<QueryLog> Context::getQueryLog()
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->query_log;
}


std::shared_ptr<QueryThreadLog> Context::getQueryThreadLog()
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->query_thread_log;
}


std::shared_ptr<PartLog> Context::getPartLog(const String & part_database)
{
    auto lock = getLock();

    /// No part log or system logs are shutting down.
    if (!shared->system_logs)
        return {};

    /// Will not log operations on system tables (including part_log itself).
    /// It doesn't make sense and not allow to destruct PartLog correctly due to infinite logging and flushing,
    /// and also make troubles on startup.
    if (part_database == DatabaseCatalog::SYSTEM_DATABASE)
        return {};

    return shared->system_logs->part_log;
}


std::shared_ptr<TraceLog> Context::getTraceLog()
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->trace_log;
}


std::shared_ptr<TextLog> Context::getTextLog()
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->text_log;
}


std::shared_ptr<MetricLog> Context::getMetricLog()
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->metric_log;
}


std::shared_ptr<AsynchronousMetricLog> Context::getAsynchronousMetricLog() const
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->asynchronous_metric_log;
}


std::shared_ptr<OpenTelemetrySpanLog> Context::getOpenTelemetrySpanLog()
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->opentelemetry_span_log;
}


std::shared_ptr<FunctionABTestLog> Context::getFunctionABTestLog() const
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->function_abtest_log;
}


std::shared_ptr<ZooKeeperLog> Context::getZooKeeperLog() const
{
    auto lock = getLock();

    if (!shared->system_logs)
        return {};

    return shared->system_logs->zookeeper_log;
}


CompressionCodecPtr Context::chooseCompressionCodec(size_t part_size, double part_size_ratio) const
{
    auto lock = getLock();

    if (!shared->compression_codec_selector)
    {
        constexpr auto config_name = "compression";
        const auto & config = getConfigRef();

        if (config.has(config_name))
            shared->compression_codec_selector = std::make_unique<CompressionCodecSelector>(config, "compression");
        else
            shared->compression_codec_selector = std::make_unique<CompressionCodecSelector>();
    }

    return shared->compression_codec_selector->choose(part_size, part_size_ratio);
}


DiskPtr Context::getDisk(const String & name) const
{
    std::lock_guard lock(shared->storage_policies_mutex);

    auto disk_selector = getDiskSelector(lock);

    return disk_selector->get(name);
}

StoragePolicyPtr Context::getStoragePolicy(const String & name) const
{
    std::lock_guard lock(shared->storage_policies_mutex);

    auto policy_selector = getStoragePolicySelector(lock);

    return policy_selector->get(name);
}


DisksMap Context::getDisksMap() const
        return storage_id;

    StorageID resolved = StorageID::createEmpty();
    std::optional<Exception> exc;
    {
        auto lock = getLock();
        resolved = resolveStorageIDImpl(std::move(storage_id), where, &exc);
    }
    if (exc)
        throw Exception(*exc);
    if (!resolved.hasUUID() && resolved.database_name != DatabaseCatalog::TEMPORARY_DATABASE)
        resolved.uuid = DatabaseCatalog::instance().getDatabase(resolved.database_name)->tryGetTableUUID(resolved.table_name);
    return resolved;
}

StorageID Context::tryResolveStorageID(StorageID storage_id, StorageNamespace where) const
{
    if (storage_id.uuid != UUIDHelpers::Nil)
        return storage_id;

    StorageID resolved = StorageID::createEmpty();
    {
        auto lock = getLock();
        resolved = resolveStorageIDImpl(std::move(storage_id), where, nullptr);
    }
    if (resolved && !resolved.hasUUID() && resolved.database_name != DatabaseCatalog::TEMPORARY_DATABASE)
    {
        auto db = DatabaseCatalog::instance().tryGetDatabase(resolved.database_name);
        if (db)
            resolved.uuid = db->tryGetTableUUID(resolved.table_name);
    }
    return resolved;
}

StorageID Context::resolveStorageIDImpl(StorageID storage_id, StorageNamespace where, std::optional<Exception> * exception) const
{
    if (storage_id.uuid != UUIDHelpers::Nil)
        return storage_id;

    if (!storage_id)
    {
        if (exception)
            exception->emplace("Both table name and UUID are empty", ErrorCodes::UNKNOWN_TABLE);
        return storage_id;
    }

    bool look_for_external_table = where & StorageNamespace::ResolveExternal;
    bool in_current_database = where & StorageNamespace::ResolveCurrentDatabase;
    bool in_specified_database = where & StorageNamespace::ResolveGlobal;

    if (!storage_id.database_name.empty())
    {
        if (in_specified_database)
            return storage_id;     /// NOTE There is no guarantees that table actually exists in database.
        if (exception)
            exception->emplace("External and temporary tables have no database, but " +
                        storage_id.database_name + " is specified", ErrorCodes::UNKNOWN_TABLE);
        return StorageID::createEmpty();
    }

    /// Database name is not specified. It's temporary table or table in current database.

    if (look_for_external_table)
    {
        /// Global context should not contain temporary tables
        assert(!isGlobalContext() || getApplicationType() == ApplicationType::LOCAL);

        auto resolved_id = StorageID::createEmpty();
        auto try_resolve = [&](ContextConstPtr context) -> bool
        {
            const auto & tables = context->external_tables_mapping;
            auto it = tables.find(storage_id.getTableName());
            if (it == tables.end())
                return false;
            resolved_id = it->second->getGlobalTableID();
            return true;
        };

        /// Firstly look for temporary table in current context
        if (try_resolve(shared_from_this()))
            return resolved_id;

        /// If not found and current context was created from some query context, look for temporary table in query context
        auto query_context_ptr = query_context.lock();
        bool is_local_context = query_context_ptr && query_context_ptr.get() != this;
        if (is_local_context && try_resolve(query_context_ptr))
            return resolved_id;

        /// If not found and current context was created from some session context, look for temporary table in session context
        auto session_context_ptr = session_context.lock();
        bool is_local_or_query_context = session_context_ptr && session_context_ptr.get() != this;
        if (is_local_or_query_context && try_resolve(session_context_ptr))
            return resolved_id;
    }

    /// Temporary table not found. It's table in current database.

    if (in_current_database)
    {
        if (current_database.empty())
        {
            if (exception)
                exception->emplace("Default database is not selected", ErrorCodes::UNKNOWN_DATABASE);
            return StorageID::createEmpty();
        }
        storage_id.database_name = current_database;
        /// NOTE There is no guarantees that table actually exists in database.
        return storage_id;
    }

    if (exception)
        exception->emplace("Cannot resolve database name for table " + storage_id.getNameForLogs(), ErrorCodes::UNKNOWN_TABLE);
    return StorageID::createEmpty();
}

void Context::initZooKeeperMetadataTransaction(ZooKeeperMetadataTransactionPtr txn, [[maybe_unused]] bool attach_existing)
{
    assert(!metadata_transaction);
    assert(attach_existing || query_context.lock().get() == this);
    metadata_transaction = std::move(txn);
}

ZooKeeperMetadataTransactionPtr Context::getZooKeeperMetadataTransaction() const
{
    assert(!metadata_transaction || hasQueryContext());
    return metadata_transaction;
}

PartUUIDsPtr Context::getPartUUIDs()
{
    auto lock = getLock();
    if (!part_uuids)
        part_uuids = std::make_shared<PartUUIDs>();

    return part_uuids;
}


ReadTaskCallback Context::getReadTaskCallback() const
{
    if (!next_task_callback.has_value())
        throw Exception(fmt::format("Next task callback is not set for query {}", getInitialQueryId()), ErrorCodes::LOGICAL_ERROR);
    return next_task_callback.value();
}


void Context::setReadTaskCallback(ReadTaskCallback && callback)
{
    next_task_callback = callback;
}

PartUUIDsPtr Context::getIgnoredPartUUIDs()
{
    auto lock = getLock();
    if (!ignored_part_uuids)
        ignored_part_uuids = std::make_shared<PartUUIDs>();

    return ignored_part_uuids;
}

}
