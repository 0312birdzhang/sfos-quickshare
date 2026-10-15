plugins { alias(libs.plugins.kotlin.jvm); application }
kotlin { jvmToolchain(17) }
dependencies {
    implementation(project(":core-protocol"))
    implementation("com.google.code.gson:gson:2.11.0")
    testImplementation(libs.junit.jupiter.api)
    testRuntimeOnly(libs.junit.jupiter.engine)
}
application { mainClass.set("org.sailfishos.quickshare.MainKt") }
tasks.withType<Test>().configureEach { useJUnitPlatform() }
