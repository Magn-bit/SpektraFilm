plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "com.spektra.film"
    compileSdk = 35
    ndkVersion = "27.2.12479018"
    defaultConfig { applicationId = "com.spektra.film"; minSdk = 26; targetSdk = 35; versionCode = 23; versionName = "0.5.0"; testInstrumentationRunner = "com.spektra.film.EngineSmokeInstrumentation" }
    defaultConfig {
        ndk { abiFilters += listOf("arm64-v8a") }
        externalNativeBuild { cmake { cppFlags += listOf("-std=c++17") } }
    }
    externalNativeBuild { cmake { path = file("src/main/cpp/CMakeLists.txt"); version = "3.22.1" } }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    sourceSets["main"].assets.setSrcDirs(listOf("src/main/assets",layout.buildDirectory.dir("generated/nativeAssets"),layout.buildDirectory.dir("generated/interfaceAssets")))
    providers.gradleProperty("personalFontsDir").orNull?.let { sourceSets["main"].assets.srcDir(it) }
    buildTypes { release { isMinifyEnabled = false } }
}
val prepareNativeSpectralAssets=tasks.register<Sync>("prepareNativeSpectralAssets") {
    from("../../native/engine/runtime/resources")
    from("../../vendor/spektrafilm/data/profile_extensions/manifest.json") {rename {"profile_extensions.json"}}
    into(layout.buildDirectory.dir("generated/nativeAssets/native_engine"))
    doFirst {
        check(file("../../native/engine/runtime/resources/vulkan/spk_curves.spv").isFile) {"Build/stage native/engine/runtime/resources before Android packaging"}
    }
}
tasks.named("preBuild").configure {dependsOn(prepareNativeSpectralAssets)}
val prepareInterfaceAssets=tasks.register<Sync>("prepareInterfaceAssets") {
    from("../../assets") {
        include("darkroom.json","styles/**","luts/manifest.json","luts/CHANGELOG.txt","color/**",
            "fonts/SpektraBilingualSerif-Regular.ttf","fonts/interface-font.json","fonts/*LICENSE*","fonts/*OFL*","fonts/OFL.txt")
    }
    into(layout.buildDirectory.dir("generated/interfaceAssets"))
}
tasks.named("preBuild").configure {dependsOn(prepareInterfaceAssets)}
