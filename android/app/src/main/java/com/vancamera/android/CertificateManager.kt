package com.vancamera.android

import android.content.Context
import android.util.Base64
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.cert.X509v3CertificateBuilder
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import org.conscrypt.Conscrypt
import java.io.File
import java.math.BigInteger
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.SecureRandom
import java.security.cert.Certificate
import java.security.cert.X509Certificate
import java.util.Date
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext

/**
 * Gestor de certificados TLS para conexiones seguras
 * Genera certificados auto-firmados automáticamente usando BouncyCastle
 */
class CertificateManager(private val context: Context) {

    companion object {
        private const val KEY_ALIAS = "vancamera_key"
        private const val CERTIFICATE_FILE = "vancamera_cert.pem"
        private const val KEYSTORE_FILE = "vancamera_keystore.jks"
        private const val KEYSTORE_PASSWORD = "vancamera_secure_password"
        private const val KEY_SIZE = 2048
        private const val VALIDITY_YEARS = 10
    }

    init {
        // Instalar Conscrypt como provider de seguridad para TLS 1.3
        try {
            Conscrypt.newProvider().let { provider ->
                java.security.Security.insertProviderAt(provider, 1)
            }
        } catch (e: Exception) {
            // Si Conscrypt no está disponible, continuar sin él
            // Android 10+ tiene soporte nativo para TLS 1.3
        }
    }

    /**
     * Genera o recupera un certificado auto-firmado
     */
    suspend fun getOrCreateCertificate(): Certificate = withContext(Dispatchers.IO) {
        try {
            val certFile = File(context.filesDir, CERTIFICATE_FILE)

            // Si el archivo PEM existe, intentar cargarlo
            if (certFile.exists()) {
                try {
                    val certFactory = java.security.cert.CertificateFactory.getInstance("X.509")
                    val cert = certFactory.generateCertificate(certFile.inputStream())
                    return@withContext cert
                } catch (e: Exception) {
                    // Si falla, generar uno nuevo
                }
            }

            // Generar nuevo certificado
            generateNewCertificate()
        } catch (e: Exception) {
            // Si hay error, generar nuevo certificado
            generateNewCertificate()
        }
    }

    /**
     * Genera un nuevo certificado auto-firmado usando BouncyCastle
     */
    private fun generateNewCertificate(): Certificate {
        // Generar par de claves RSA
        val keyPairGenerator = KeyPairGenerator.getInstance("RSA")
        keyPairGenerator.initialize(KEY_SIZE, SecureRandom())
        val keyPair = keyPairGenerator.generateKeyPair()

        // Crear certificado X.509 usando BouncyCastle
        val issuer = X500Name("CN=VanCamera, O=VanCamera, C=US")
        val subject = X500Name("CN=VanCamera, O=VanCamera, C=US")
        val serialNumber = BigInteger(64, SecureRandom())
        val notBefore = Date()
        val notAfter = Date(System.currentTimeMillis() + VALIDITY_YEARS * 365L * 24L * 60L * 60L * 1000L)

        val certBuilder = X509v3CertificateBuilder(
            issuer,
            serialNumber,
            notBefore,
            notAfter,
            subject,
            org.bouncycastle.asn1.x509.SubjectPublicKeyInfo.getInstance(
                org.bouncycastle.asn1.pkcs.PrivateKeyInfo.getInstance(keyPair.public.encoded)
            )
        )

        // Firmar el certificado
        val signer = JcaContentSignerBuilder("SHA256withRSA")
            .setProvider("BC")
            .build(keyPair.private)

        val certHolder = certBuilder.build(signer)

        // Convertir a X509Certificate de Java
        val certConverter = JcaX509CertificateConverter()
            .setProvider("BC")
        val cert = certConverter.getCertificate(certHolder) as X509Certificate

        // Guardar en keystore
        val keystore = KeyStore.getInstance("JKS")
        keystore.load(null, null)
        val certChain = arrayOf<Certificate>(cert)
        keystore.setKeyEntry(KEY_ALIAS, keyPair.private, KEYSTORE_PASSWORD.toCharArray(), certChain)

        val keystoreFile = File(context.filesDir, KEYSTORE_FILE)
        keystore.store(keystoreFile.outputStream(), KEYSTORE_PASSWORD.toCharArray())

        // Guardar certificado público en archivo para compartir con Windows
        savePublicCertificate(cert)

        return cert
    }

    /**
     * Guarda el certificado público en formato PEM para compartir con Windows
     */
    private fun savePublicCertificate(certificate: Certificate) {
        val certFile = File(context.filesDir, CERTIFICATE_FILE)
        val certBytes = certificate.encoded
        val pemString = buildString {
            appendLine("-----BEGIN CERTIFICATE-----")
            // Dividir en líneas de 64 caracteres
            val base64 = Base64.encodeToString(certBytes, Base64.NO_WRAP)
            base64.chunked(64).forEach { chunk ->
                appendLine(chunk)
            }
            appendLine("-----END CERTIFICATE-----")
        }
        certFile.writeText(pemString)
    }

    /**
     * Obtiene el certificado público en formato PEM como String
     */
    suspend fun getPublicCertificatePem(): String = withContext(Dispatchers.IO) {
        val certFile = File(context.filesDir, CERTIFICATE_FILE)
        if (certFile.exists()) {
            certFile.readText()
        } else {
            // Si no existe, generar uno nuevo
            getOrCreateCertificate()
            certFile.readText()
        }
    }

    /**
     * Obtiene el certificado público en formato Base64 (sin headers PEM)
     */
    suspend fun getPublicCertificateBase64(): String = withContext(Dispatchers.IO) {
        val cert = getOrCreateCertificate()
        Base64.encodeToString(cert.encoded, Base64.NO_WRAP)
    }

    /**
     * Regenera el certificado (útil si se necesita uno nuevo)
     */
    suspend fun regenerateCertificate(): Certificate = withContext(Dispatchers.IO) {
        try {
            val certFile = File(context.filesDir, CERTIFICATE_FILE)
            if (certFile.exists()) {
                certFile.delete()
            }
            val keystoreFile = File(context.filesDir, KEYSTORE_FILE)
            if (keystoreFile.exists()) {
                keystoreFile.delete()
            }
        } catch (e: Exception) {
            // Ignorar errores al eliminar
        }
        generateNewCertificate()
    }

    /**
     * Obtiene la ruta del archivo de certificado público
     */
    fun getCertificateFilePath(): String {
        return File(context.filesDir, CERTIFICATE_FILE).absolutePath
    }

    /**
     * Crea un SSLContext configurado con el certificado y clave privada
     */
    suspend fun createSSLContext(): SSLContext = withContext(Dispatchers.IO) {
        val keystoreFile = File(context.filesDir, KEYSTORE_FILE)
        if (!keystoreFile.exists()) {
            getOrCreateCertificate() // Esto creará el keystore
        }

        val keystore = KeyStore.getInstance("JKS")
        keystore.load(keystoreFile.inputStream(), KEYSTORE_PASSWORD.toCharArray())

        val keyManagerFactory = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())
        keyManagerFactory.init(keystore, KEYSTORE_PASSWORD.toCharArray())

        val sslContext = SSLContext.getInstance("TLSv1.3")
        sslContext.init(keyManagerFactory.keyManagers, null, SecureRandom())

        sslContext
    }

    /**
     * Obtiene el KeyPair asociado al certificado
     */
    suspend fun getKeyPair(): KeyPair? = withContext(Dispatchers.IO) {
        try {
            val keystoreFile = File(context.filesDir, KEYSTORE_FILE)
            if (!keystoreFile.exists()) {
                return@withContext null
            }

            val keystore = KeyStore.getInstance("JKS")
            keystore.load(keystoreFile.inputStream(), KEYSTORE_PASSWORD.toCharArray())

            if (keystore.containsAlias(KEY_ALIAS)) {
                val entry = keystore.getEntry(KEY_ALIAS,
                    KeyStore.PasswordProtection(KEYSTORE_PASSWORD.toCharArray())) as? KeyStore.PrivateKeyEntry
                entry?.let {
                    KeyPair(it.certificate.publicKey, it.privateKey)
                }
            } else {
                null
            }
        } catch (e: Exception) {
            null
        }
    }
}
