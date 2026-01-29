plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    id("kotlin-parcelize")
}

android {
    namespace = "com.vancamera.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.vancamera.android"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // Release signing configuration
    // Keystore credentials are read from environment variables for security
    signingConfigs {
        create("release") {
            val keystorePath = System.getenv("VANCAMERA_KEYSTORE_PATH") 
                ?: file("keystore/vancamera.jks").absolutePath
            storeFile = file(keystorePath)
            storePassword = System.getenv("VANCAMERA_KEYSTORE_PASSWORD") ?: ""
            keyAlias = System.getenv("VANCAMERA_KEY_ALIAS") ?: "vancamera"
            keyPassword = System.getenv("VANCAMERA_KEY_PASSWORD") ?: ""
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // Use release signing config if keystore exists
            val keystoreFile = file(
                System.getenv("VANCAMERA_KEYSTORE_PATH") 
                    ?: "keystore/vancamera.jks"
            )
            if (keystoreFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
        debug {
            isMinifyEnabled = false
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    kotlinOptions {
        jvmTarget = "11"
    }

    packaging {
        resources {
            // BouncyCastle jars contain duplicate metadata files under META-INF/versions/9.
            excludes += "META-INF/versions/9/OSGI-INF/MANIFEST.MF"
        }
    }
}

dependencies {
    // Core Android
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)

    // CameraX
    implementation(libs.camerax.core)
    implementation(libs.camerax.camera2)
    implementation(libs.camerax.lifecycle)
    implementation(libs.camerax.view)

    // Lifecycle
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.lifecycle.viewmodel.ktx)

    // Coroutines
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)

    // TLS 1.3 Support
    implementation(libs.conscrypt.android)

    // BouncyCastle for certificate generation
    implementation(libs.bouncycastle.bcprov)
    implementation(libs.bouncycastle.bcpkix)

    // QR Code generation
    implementation(libs.zxing.core)
    implementation(libs.zxing.android.embedded)

    // Testing
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}
