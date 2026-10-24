package `in`.chargepilot.agent

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.app.ActivityManager
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.StatFs
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.io.IOException
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.UUID
import java.util.concurrent.TimeUnit

data class BatteryReading(
    val percentage: Int,
    val charging: Boolean,
    val acConnected: Boolean?,
)

data class DiskUsage(val name: String, val usedBytes: Long, val totalBytes: Long)

data class SystemMetrics(
    val cpuUsagePercent: Double?,
    val gpuUsagePercent: Double?,
    val memoryUsedBytes: Long?,
    val memoryTotalBytes: Long?,
    val disks: List<DiskUsage>,
)

object SystemMetricsReader {
    fun read(context: Context): SystemMetrics {
        val memory = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memoryInfo = ActivityManager.MemoryInfo().also(memory::getMemoryInfo)
        val storage = StatFs(Environment.getDataDirectory().path)
        val storageTotal = storage.blockSizeLong * storage.blockCountLong
        val storageFree = storage.blockSizeLong * storage.availableBlocksLong
        return SystemMetrics(
            cpuUsagePercent = readCpuUsage(),
            gpuUsagePercent = null,
            memoryUsedBytes = (memoryInfo.totalMem - memoryInfo.availMem).coerceAtLeast(0),
            memoryTotalBytes = memoryInfo.totalMem.takeIf { it > 0 },
            disks = listOf(
                DiskUsage(
                    name = "Device storage",
                    usedBytes = (storageTotal - storageFree).coerceAtLeast(0),
                    totalBytes = storageTotal,
                ),
            ).filter { it.totalBytes > 0 },
        )
    }

    private fun readCpuUsage(): Double? {
        return try {
            val first = readCpuCounters()
            Thread.sleep(100)
            val second = readCpuCounters()
            val total = second.first - first.first
            val idle = second.second - first.second
            if (total <= 0) null else ((total - idle).toDouble() / total * 100).coerceIn(0.0, 100.0)
        } catch (error: IOException) {
            null
        } catch (error: InterruptedException) {
            Thread.currentThread().interrupt()
            null
        }
    }

    private fun readCpuCounters(): Pair<Long, Long> {
        val line = File("/proc/stat").useLines { lines -> lines.firstOrNull() }
            ?: throw IOException("CPU counters are unavailable.")
        val values = line.trim().split(Regex("\\s+")).drop(1).map(String::toLong)
        if (values.size < 5) throw IOException("CPU counters are incomplete.")
        return values.sum() to (values[3] + values[4])
    }
}

object BatteryReader {
    fun read(context: Context): BatteryReading {
        val intent = context.registerReceiver(
            null,
            IntentFilter(Intent.ACTION_BATTERY_CHANGED),
        ) ?: throw BatteryUnavailableException()
        val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        if (level < 0 || scale <= 0) throw BatteryUnavailableException()

        val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        if (status !in setOf(
                BatteryManager.BATTERY_STATUS_CHARGING,
                BatteryManager.BATTERY_STATUS_DISCHARGING,
                BatteryManager.BATTERY_STATUS_FULL,
                BatteryManager.BATTERY_STATUS_NOT_CHARGING,
            )
        ) {
            throw BatteryUnavailableException()
        }
        val plugType = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, -1)
        return BatteryReading(
            percentage = ((level.toDouble() / scale) * 100).toInt().coerceIn(0, 100),
            charging = status == BatteryManager.BATTERY_STATUS_CHARGING,
            acConnected = if (plugType < 0) null else plugType != 0,
        )
    }
}

object AgentApi {
    const val SERVER_ORIGIN = "https://api-chargepilot.endusercompute.in"

    fun enroll(
        enrollmentToken: String,
        label: String,
        installationId: String,
        deviceClass: String,
    ): Pair<String, String> {
        val body = JSONObject()
            .put("code", enrollmentToken)
            .put("platform", "android")
            .put("installation_id", installationId)
            .put("hostname", label)
            .put("device_class", deviceClass)
        val response = request(
            origin = SERVER_ORIGIN,
            path = "/api/v1/endpoint-enrollment/exchange",
            body = body,
        )
        val credential = response.optString("credential")
        val endpointId = response.optString("endpoint_id")
        val returnedInstallationId = response.optString("installation_id")
        if (
            credential.isBlank() ||
            endpointId.isBlank() ||
            returnedInstallationId != installationId
        ) {
            throw IOException("The server returned an incomplete enrollment response.")
        }
        return endpointId to credential
    }

    fun sendTelemetry(
        context: Context,
        configuration: AgentConfiguration,
        credential: String,
        reading: BatteryReading,
    ): Int {
        val metrics = SystemMetricsReader.read(context)
        val body = JSONObject()
            .put("hostname", configuration.label)
            .put("installation_id", configuration.installationId)
            .put("platform", "android")
            .put(
                "device_class",
                if (context.resources.configuration.smallestScreenWidthDp >= 600) "tablet" else "phone",
            )
            .put("battery_percentage", reading.percentage)
            .put("charging", reading.charging)
            .put("timestamp", Instant.now().toString())
            .put("agent_version", BuildConfig.VERSION_NAME)
            .put(
                "system_metrics",
                JSONObject()
                    .put("cpu_usage_percent", metrics.cpuUsagePercent ?: JSONObject.NULL)
                    .put("gpu_usage_percent", metrics.gpuUsagePercent ?: JSONObject.NULL)
                    .put("memory_used_bytes", metrics.memoryUsedBytes ?: JSONObject.NULL)
                    .put("memory_total_bytes", metrics.memoryTotalBytes ?: JSONObject.NULL)
                    .put(
                        "disks",
                        org.json.JSONArray().apply {
                            metrics.disks.forEach { disk ->
                                put(
                                    JSONObject()
                                        .put("name", disk.name)
                                        .put("used_bytes", disk.usedBytes)
                                        .put("total_bytes", disk.totalBytes),
                                )
                            }
                        },
                    ),
            )
        reading.acConnected?.let { body.put("ac_connected", it) }
        val response = request(
            origin = SERVER_ORIGIN,
            path = "/api/v1/telemetry",
            body = body,
            credential = credential,
        )
        return response.optInt("reporting_interval_seconds", DEFAULT_REPORTING_INTERVAL_SECONDS)
            .takeIf { it in MIN_REPORTING_INTERVAL_SECONDS..MAX_REPORTING_INTERVAL_SECONDS }
            ?: DEFAULT_REPORTING_INTERVAL_SECONDS
    }

    fun deregister(credential: String) {
        request(
            origin = SERVER_ORIGIN,
            path = "/api/v1/endpoint-enrollment/deregister",
            body = JSONObject(),
            credential = credential,
        )
    }

    private fun request(
        origin: String,
        path: String,
        body: JSONObject,
        credential: String? = null,
    ): JSONObject {
        val connection = (URL("$origin$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 15_000
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            credential?.let { setRequestProperty("Authorization", "Bearer $it") }
        }
        try {
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            if (status !in 200..299) {
                throw ApiRejectedException(status)
            }
            val responseText = connection.inputStream.bufferedReader().use { it.readText() }
            return if (responseText.isBlank()) JSONObject() else JSONObject(responseText)
        } finally {
            connection.disconnect()
        }
    }

    private const val DEFAULT_REPORTING_INTERVAL_SECONDS = 300
    private const val MIN_REPORTING_INTERVAL_SECONDS = 300
    private const val MAX_REPORTING_INTERVAL_SECONDS = 86_400
}

class TelemetryWorker(context: Context, parameters: WorkerParameters) : Worker(context, parameters) {
    private val store = AgentStore(context)

    override fun doWork(): Result {
        val configuration = store.configuration()
            ?: return fail("Enroll this device before sending telemetry.")
        return try {
            val reading = BatteryReader.read(applicationContext)
            val intervalSeconds = AgentApi.sendTelemetry(applicationContext, configuration, store.credential(), reading)
            store.recordSuccess(Instant.now().toString())
            store.recordReportingInterval(intervalSeconds / 60)
            schedulePeriodic(applicationContext, intervalSeconds / 60)
            Result.success()
        } catch (error: ApiRejectedException) {
            val message = "ChargePilot rejected the report (HTTP ${error.statusCode})."
            store.recordError(message)
            if (error.statusCode >= 500 && runAttemptCount < MAX_RETRIES) Result.retry() else Result.failure()
        } catch (error: BatteryUnavailableException) {
            fail("A usable battery reading is unavailable; no sample was sent.")
        } catch (error: IOException) {
            val message = "The report could not reach ChargePilot. Check the connection and try again."
            store.recordError(message)
            if (runAttemptCount < MAX_RETRIES) Result.retry() else Result.failure()
        } catch (_: Exception) {
            fail("The report could not be prepared. Check enrollment and device storage.")
        }
    }

    private fun fail(message: String): Result {
        store.recordError(message)
        return Result.failure()
    }

    companion object {
        private const val MAX_RETRIES = 3
        private const val PERIODIC_REPORT = "chargepilot-periodic-telemetry"

        fun schedulePeriodic(context: Context, reportingIntervalMinutes: Int = 15) {
            val effectiveIntervalMinutes = reportingIntervalMinutes.coerceIn(15, 1440)
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = PeriodicWorkRequestBuilder<TelemetryWorker>(effectiveIntervalMinutes.toLong(), TimeUnit.MINUTES)
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .addTag(TELEMETRY_WORK_TAG)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                PERIODIC_REPORT,
                ExistingPeriodicWorkPolicy.UPDATE,
                request,
            )
        }

        fun sendNow(context: Context): UUID {
            val request = OneTimeWorkRequestBuilder<TelemetryWorker>()
                .addTag(TELEMETRY_WORK_TAG)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueue(request)
            return request.id
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(PERIODIC_REPORT)
            WorkManager.getInstance(context).cancelAllWorkByTag(TELEMETRY_WORK_TAG)
        }

        private const val TELEMETRY_WORK_TAG = "chargepilot-telemetry"
    }
}

class ApiRejectedException(val statusCode: Int) : IOException()
class BatteryUnavailableException : IOException()
