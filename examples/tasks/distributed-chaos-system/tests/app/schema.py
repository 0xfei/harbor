def normalize_event(e):

    if "user_id" in e:
        return e

    if "uid" in e:
        e["user_id"] = e["uid"]

    return e