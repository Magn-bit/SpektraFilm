#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct spk_raw_result {
    const float* rgb;
    uint32_t width, height;
    void* owner;
    const char* metadata_json;
} spk_raw_result;
/* Metadata only, no sensor unpack. Thread-local borrowed JSON, valid until
 * the next raw probe on this thread. A failed probe returns NULL. */
const char* spk_raw_probe(const char* path_utf8);
/* policy: auto, headroom or compatible16. Auto routes known conventional
 * Bayer to headroom and other layouts to compatible16 before sensor unpack;
 * the exact selected policy/reason is returned in metadata, never concealed.
 * half_size is exclusively a preview proxy; final callers must pass zero. */
int32_t spk_raw_decode(const char* path_utf8,const char* policy,int32_t half_size,spk_raw_result* out);
void spk_raw_free(spk_raw_result* result);
const char* spk_raw_last_error(void);
#ifdef __cplusplus
}
#endif
