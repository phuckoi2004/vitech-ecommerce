"""Explicit product requirements, checked against catalog facts before ranking."""

import re

from app.core.search_text import fold


FEATURE_LABELS = {"anc": "chống ồn chủ động ANC", "gaming_laptop": "laptop gaming"}


def required_features(question):
    text = fold(question)
    result = []
    if (re.search(r"\b(?:chong on|anc|active noise cancel(?:ling|lation))\b", text)
            and not re.search(r"\b(?:khong can|khong yeu cau|bo (?:loc|yeu cau))\b.*\b(?:chong on|anc)\b", text)
            and not re.search(r"\b(?:chong on (?:cuoc goi|dam thoai|micro)|enc)\b", text)):
        result.append("anc")
    if re.search(r"\blaptop gaming\b", text):
        result.append("gaming_laptop")
    return tuple(result)


def _leaves(data, depth=0):
    if not isinstance(data, dict) or depth > 3:
        return
    for key, value in list(data.items())[:100]:
        if isinstance(value, dict):
            yield from _leaves(value, depth + 1)
        elif isinstance(value, (str, int, float, bool)):
            yield fold(str(key)), fold(str(value))
        elif isinstance(value, list):
            yield fold(str(key)), fold("; ".join(str(v) for v in value[:20]))


def feature_evidence(detail, feature):
    if feature == "gaming_laptop":
        # A request for the gaming product class is stricter than the soft need "chơi game".
        if re.search(r"\bgaming\b", fold(detail.Category.Name)):
            return "Danh mục laptop gaming"
        for key, value in _leaves(detail.Specifications):
            if re.search(r"\b(?:gpu|vga|graphics|card do hoa)\b", key) and re.search(
                    r"\b(?:geforce|rtx|gtx|radeon rx|arc a\d+|arc b\d+)\b", value):
                return "GPU rời: " + value[:100]
        return None
    if feature != "anc":
        return None
    for key, value in [("ten san pham", fold(detail.Name)), *_leaves(detail.Specifications)]:
        if re.search(r"\b(?:pin|battery|thoi luong|micro|cuoc goi|dam thoai)\b", key):
            continue
        for clause in re.split(r"[;\n]", value):
            text = f"{key}: {clause}" if key in ("anc", "chong on chu dong") else clause
            if (re.search(r"\b(?:anc|chong on chu dong|active noise cancel(?:ling|lation))\b", text)
                    and not re.search(r"\b(?:khong|chua|false|no|none|khong co|tat anc|anc off)\b", text)):
                return "Có chống ồn chủ động ANC"
    return None


def meets_features(detail, features):
    return all(feature_evidence(detail, feature) for feature in features)
