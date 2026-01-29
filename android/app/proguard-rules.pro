# Add project specific ProGuard rules here.
# You can control the set of applied configuration files using the
# proguardFiles setting in build.gradle.
#
# For more details, see
#   http://developer.android.com/guide/developing/tools/proguard.html

# If your project uses WebView with JS, uncomment the following
# and specify the fully qualified class name to the JavaScript interface
# class:
#-keepclassmembers class fqcn.of.javascript.interface.for.webview {
#   public *;
#}

# Uncomment this to preserve the line number information for
# debugging stack traces.
#-keepattributes SourceFile,LineNumberTable

# If you keep the line number information, uncomment this to
# hide the original source file name.
#-renamesourcefileattribute SourceFile

# ============================================
# Conscrypt (TLS 1.3 support)
# ============================================
-keep class org.conscrypt.** { *; }
-dontwarn org.conscrypt.**
-dontwarn com.android.org.conscrypt.**
-dontwarn org.apache.harmony.xnet.provider.jsse.**

# ============================================
# BouncyCastle (Certificate generation)
# ============================================
-keep class org.bouncycastle.** { *; }
-dontwarn org.bouncycastle.**

# ============================================
# ZXing (QR Code)
# ============================================
-keep class com.google.zxing.** { *; }
-dontwarn com.google.zxing.**

# ============================================
# Keep app classes
# ============================================
-keep class com.vancamera.android.** { *; }
