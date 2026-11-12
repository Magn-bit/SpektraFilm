pluginManagement {
    val localRepo = System.getenv("SPEKTRAFILM_MAVEN_REPO")
        ?: System.getenv("LOCALAPPDATA")?.let { "$it/SpektraFilmDev/maven" }
    repositories {
        if (localRepo != null) maven { url = uri(localRepo) }
        google(); mavenCentral(); gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    val localRepo = System.getenv("SPEKTRAFILM_MAVEN_REPO")
        ?: System.getenv("LOCALAPPDATA")?.let { "$it/SpektraFilmDev/maven" }
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        if (localRepo != null) maven { url = uri(localRepo) }
        google(); mavenCentral()
    }
}
rootProject.name = "SpektraFilm"
include(":app")
