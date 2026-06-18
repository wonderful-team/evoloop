#pragma once
#include <unordered_map>
#include <string>

namespace butter {
    template <typename K, typename V>
    using map = std::unordered_map<K, V>;
}
