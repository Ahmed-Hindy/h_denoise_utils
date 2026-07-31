#pragma once

#include <array>
#include <cstdint>

namespace hdu::oidn_bridge {

constexpr std::array<char, 8> kMagic = {'H', 'D', 'U', 'O', 'I', 'D', 'N', '1'};
constexpr std::uint32_t kVersion = 1;
constexpr std::uint32_t kHasAlbedo = 1U << 0U;
constexpr std::uint32_t kHasNormal = 1U << 1U;
constexpr std::uint32_t kHdr = 1U << 2U;
constexpr std::uint32_t kCleanAux = 1U << 3U;

#pragma pack(push, 1)
struct Header {
    std::array<char, 8> magic = kMagic;
    std::uint32_t version = kVersion;
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    std::uint32_t flags = 0;
    std::uint32_t quality = 2;
    std::uint32_t reserved = 0;
};
#pragma pack(pop)

static_assert(sizeof(Header) == 32);

}  // namespace hdu::oidn_bridge
