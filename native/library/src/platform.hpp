// SpektraFilm Windows portability additions to SpektraLab_library (MIT).
#pragma once

#include <cerrno>
#include <ctime>
#include <filesystem>
#include <stdexcept>
#include <string>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace spklib::platform {

inline std::string generic_path(const std::string& value) {
    return std::filesystem::u8path(value).lexically_normal().generic_u8string();
}

inline bool exists(const std::string& value) {
    std::error_code ec;
    return std::filesystem::exists(std::filesystem::u8path(value), ec);
}

#ifdef _WIN32
inline std::wstring wide(const std::string& value) {
    if (value.empty()) return {};
    const int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), int(value.size()), nullptr, 0);
    if (!n) throw std::runtime_error("invalid UTF-8 path");
    std::wstring out(size_t(n), L'\0');
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), int(value.size()), out.data(), n);
    return out;
}

inline std::string utf8(const std::wstring& value) {
    if (value.empty()) return {};
    const int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), int(value.size()), nullptr, 0, nullptr, nullptr);
    if (!n) throw std::runtime_error("invalid UTF-16 path");
    std::string out(size_t(n), '\0');
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), int(value.size()), out.data(), n, nullptr, nullptr);
    return out;
}

inline std::string normalize_unicode(const std::string& value) {
    const auto source = wide(value);
    int n = NormalizeString(NormalizationC, source.data(), int(source.size()), nullptr, 0);
    if (n <= 0) return value;
    std::wstring out(size_t(n), L'\0');
    n = NormalizeString(NormalizationC, source.data(), int(source.size()), out.data(), n);
    if (n <= 0) return value;
    out.resize(size_t(n));
    return utf8(out);
}

inline std::tm* utc_time(const std::time_t* t, std::tm* out) { return gmtime_s(out, t) == 0 ? out : nullptr; }
inline std::tm* local_time(const std::time_t* t, std::tm* out) { return localtime_s(out, t) == 0 ? out : nullptr; }
inline std::time_t time_utc(std::tm* t) { return _mkgmtime(t); }

// The flags deliberately omit MOVEFILE_COPY_ALLOWED and MOVEFILE_REPLACE_EXISTING:
// a session move must remain atomic and may never overwrite a photograph.
inline int move_exclusive(const std::string& from, const std::filesystem::path& to) {
    if (MoveFileExW(wide(from).c_str(), to.c_str(), MOVEFILE_WRITE_THROUGH)) return 0;
    const DWORD error = GetLastError();
    errno = error == ERROR_NOT_SAME_DEVICE ? EXDEV
          : error == ERROR_FILE_EXISTS || error == ERROR_ALREADY_EXISTS ? EEXIST
          : error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND ? ENOENT
          : error == ERROR_ACCESS_DENIED || error == ERROR_SHARING_VIOLATION ? EACCES : EIO;
    return -1;
}
#else
inline std::tm* utc_time(const std::time_t* t, std::tm* out) { return gmtime_r(t, out); }
inline std::tm* local_time(const std::time_t* t, std::tm* out) { return localtime_r(t, out); }
inline std::time_t time_utc(std::tm* t) { return timegm(t); }
#endif

}  // namespace spklib::platform
