// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "core.h"
#include <map>
namespace quickshare {
// Deliberately bounded JSON subset for the local worker pipe: strings, integer
// configuration values, booleans, null, arrays and objects. No implicit coercion.
struct Json {
    enum Kind { Null, String, Number, Boolean, Array, Object } kind = Null;
    std::string text;
    std::int64_t number = 0;
    bool boolean = false;
    std::vector<Json> array;
    std::map<std::string,Json> object;
    const Json &at(const std::string &key) const;
    std::string string() const;
    std::int64_t integer() const;
    bool flag() const;
    bool has(const std::string &key) const;
};
bool validUtf8(const std::string &value);
Json parseJson(const std::string &value);
std::string quoteJson(const std::string &value);
}
