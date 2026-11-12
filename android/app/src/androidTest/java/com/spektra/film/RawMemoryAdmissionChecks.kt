package com.spektra.film

/** Synthetic policy checks: no Bitmap, sensor buffer, or large file is allocated. */
internal fun verifyRawMemoryAdmission() {
    val mib = 1024L * 1024
    val gib = 1024L * mib
    val sensorWidth = 9600L
    val sensorHeight = 6400L
    val expected = sensorWidth * sensorHeight * 12 + 288L * mib
    val roomy = rawMemoryAdmission(sensorWidth, sensorHeight, 5L * gib, 8L * gib, false)
    check(roomy.estimatedPeakBytes == expected && roomy.budgetBytes == 2L * gib)
    fun rejects(width: Long = sensorWidth, height: Long = sensorHeight, available: Long = 5L * gib,
                total: Long = 8L * gib, lowMemory: Boolean = false) {
        val failure = runCatching { rawMemoryAdmission(width, height, available, total, lowMemory) }.exceptionOrNull()
        check(failure is IllegalStateException && failure.message.orEmpty().contains("原片未缩小") && failure.message.orEmpty().contains("RAW 原片另存"))
    }
    val fourGib = rawMemoryAdmission(sensorWidth, sensorHeight, 3L * gib, 4L * gib, false)
    check(fourGib.budgetBytes == gib && fourGib.estimatedPeakBytes == expected)
    rejects(available = 2L * gib, total = 3L * gib) // Total RAM quarter caps the budget.
    rejects(available = gib) // Available RAM sixty-percent caps the budget.
    rejects(lowMemory = true)
    rejects(available = 0)
    rejects(total = 0)
    rejects(available = 9L * gib)
    rejects(width = 0)
    rejects(width = Long.MAX_VALUE, height = 2) // Sensor area multiplication overflow.
    rejects(width = Long.MAX_VALUE / 12 + 1, height = 1) // Native bytes multiplication overflow.
    rejects(width = Long.MAX_VALUE / 12, height = 1) // Reserve addition overflow.
    val hugeMetric = rawMemoryAdmission(1, 1, Long.MAX_VALUE, Long.MAX_VALUE, false)
    check(hugeMetric.budgetBytes == Long.MAX_VALUE / 4)
    val exact = rawMemoryAdmission(1, 1, 4 * (288L * mib + 12), 4 * (288L * mib + 12), false)
    check(exact.estimatedPeakBytes == exact.budgetBytes)
    rejects(width = 1, height = 1, available = 4 * (288L * mib + 12) - 1, total = 4 * (288L * mib + 12) - 1)
}
