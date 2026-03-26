from dataclasses import dataclass


@dataclass(slots=True)
class FingerprintProfile:
    user_agent: str
    language: str = "en-US"
    color_depth: int = 24
    screen_width: int = 1920
    screen_height: int = 1080
    timezone_offset: int = 0
    has_session_storage: bool = True
    has_local_storage: bool = True
    has_indexed_db: bool = True
    add_behavior_type: str = "undefined"
    open_database_type: str = "function"
    cpu_class: str = ""
    platform: str = "MacIntel"
    do_not_track: str = ""
    plugins_string: str = ""
    canvas_fingerprint: str = ""

    @classmethod
    def from_config(cls, config: dict) -> "FingerprintProfile":
        return cls(
            user_agent=config["user_agent"],
            language=config.get("language", "en-US"),
            color_depth=int(config.get("color_depth", 24)),
            screen_width=int(config.get("screen_width", 1920)),
            screen_height=int(config.get("screen_height", 1080)),
            timezone_offset=int(config.get("timezone_offset", 0)),
            has_session_storage=bool(config.get("has_session_storage", True)),
            has_local_storage=bool(config.get("has_local_storage", True)),
            has_indexed_db=bool(config.get("has_indexed_db", True)),
            add_behavior_type=config.get("add_behavior_type", "undefined"),
            open_database_type=config.get("open_database_type", "function"),
            cpu_class=config.get("cpu_class", ""),
            platform=config.get("platform", "MacIntel"),
            do_not_track=config.get("do_not_track", ""),
            plugins_string=config.get("plugins_string", ""),
            canvas_fingerprint=config.get("canvas_fingerprint", ""),
        )


def octofence_fp_value(profile: FingerprintProfile) -> str:
    parts = [
        profile.user_agent,
        profile.language,
        str(profile.color_depth),
        f"{profile.screen_height}x{profile.screen_width}",
        str(profile.timezone_offset),
        str(profile.has_session_storage).lower(),
        str(profile.has_local_storage).lower(),
        str(profile.has_indexed_db).lower(),
        profile.add_behavior_type,
        profile.open_database_type,
        profile.cpu_class,
        profile.platform,
        profile.do_not_track,
        profile.plugins_string,
    ]
    if profile.canvas_fingerprint:
        parts.append(profile.canvas_fingerprint)
    return str(murmurhash3_32_gc("###".join(parts), 31))


def murmurhash3_32_gc(key: str, seed: int) -> int:
    remainder = len(key) & 3
    length = len(key) - remainder
    h1 = seed
    c1 = 0xCC9E2D51
    c2 = 0x1B873593
    i = 0

    while i < length:
        k1 = (
            (ord(key[i]) & 0xFF)
            | ((ord(key[i + 1]) & 0xFF) << 8)
            | ((ord(key[i + 2]) & 0xFF) << 16)
            | ((ord(key[i + 3]) & 0xFF) << 24)
        )
        i += 4

        k1 = (((k1 & 0xFFFF) * c1) + ((((k1 >> 16) * c1) & 0xFFFF) << 16)) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (((k1 & 0xFFFF) * c2) + ((((k1 >> 16) * c2) & 0xFFFF) << 16)) & 0xFFFFFFFF

        h1 ^= k1
        h1 = ((h1 << 13) | (h1 >> 19)) & 0xFFFFFFFF
        h1b = (((h1 & 0xFFFF) * 5) + ((((h1 >> 16) * 5) & 0xFFFF) << 16)) & 0xFFFFFFFF
        h1 = (((h1b & 0xFFFF) + 0x6B64) + ((((h1b >> 16) + 0xE654) & 0xFFFF) << 16)) & 0xFFFFFFFF

    k1 = 0
    if remainder == 3:
        k1 ^= (ord(key[i + 2]) & 0xFF) << 16
    if remainder >= 2:
        k1 ^= (ord(key[i + 1]) & 0xFF) << 8
    if remainder >= 1:
        k1 ^= ord(key[i]) & 0xFF
        k1 = (((k1 & 0xFFFF) * c1) + ((((k1 >> 16) * c1) & 0xFFFF) << 16)) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (((k1 & 0xFFFF) * c2) + ((((k1 >> 16) * c2) & 0xFFFF) << 16)) & 0xFFFFFFFF
        h1 ^= k1

    h1 ^= len(key)
    h1 ^= h1 >> 16
    h1 = (((h1 & 0xFFFF) * 0x85EBCA6B) + ((((h1 >> 16) * 0x85EBCA6B) & 0xFFFF) << 16)) & 0xFFFFFFFF
    h1 ^= h1 >> 13
    h1 = (((h1 & 0xFFFF) * 0xC2B2AE35) + ((((h1 >> 16) * 0xC2B2AE35) & 0xFFFF) << 16)) & 0xFFFFFFFF
    h1 ^= h1 >> 16
    return h1 & 0xFFFFFFFF
