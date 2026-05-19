package systems.xt.agixt.desktop

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager as AndroidBluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Base64
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.NotificationCompat
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import app.tauri.annotation.Command
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import java.io.ByteArrayOutputStream
import java.text.SimpleDateFormat
import java.util.ArrayDeque
import java.util.Date
import java.util.Locale
import java.util.TreeMap
import java.util.TimeZone
import java.util.UUID

internal data class G1KeepAliveSnapshot(
  val maintaining: Boolean,
  val leftConnected: Boolean,
  val rightConnected: Boolean,
  val lastEvent: String?,
  val lastError: String?,
)

@SuppressLint("MissingPermission")
@TauriPlugin
class G1Plugin(private val activity: Activity) : Plugin(activity) {
  private enum class Side(val wireName: String) {
    LEFT("left"),
    RIGHT("right")
  }

  private data class BatteryInfo(
    val side: Side,
    val percentage: Int,
    val voltage: Int,
    val isCharging: Boolean,
    val timestamp: String,
  ) {
    fun toJson(): JSObject = JSObject()
      .put("side", side.wireName)
      .put("percentage", percentage)
      .put("voltage", voltage)
      .put("is_charging", isCharging)
      .put("timestamp", timestamp)
  }

  private data class QueuedWrite(
    val data: ByteArray,
    val callback: (Boolean, String?) -> Unit,
  )

  private inner class GlassConnection(
    val side: Side,
    var name: String,
    val id: String,
    val device: BluetoothDevice,
  ) {
    var gatt: BluetoothGatt? = null
    var tx: BluetoothGattCharacteristic? = null
    var rx: BluetoothGattCharacteristic? = null
    var connected: Boolean = false
    var timeout: Runnable? = null

    private val writeQueue = ArrayDeque<QueuedWrite>()
    private var pendingWrite: QueuedWrite? = null

    fun summary(): JSObject = JSObject()
      .put("side", side.wireName)
      .put("name", name)
      .put("id", id)
      .put("connected", connected)

    fun enqueueWrite(data: ByteArray, callback: (Boolean, String?) -> Unit) {
      mainHandler.post {
        writeQueue.add(QueuedWrite(data, callback))
        drainWrites()
      }
    }

    fun handleWrite(status: Int) {
      mainHandler.post {
        val finished = pendingWrite
        pendingWrite = null
        if (finished != null) {
          if (status == BluetoothGatt.GATT_SUCCESS) {
            finished.callback(true, null)
          } else {
            finished.callback(false, "${side.wireName} GATT write failed with status $status")
          }
        }
        drainWrites()
      }
    }

    fun close() {
      timeout?.let { mainHandler.removeCallbacks(it) }
      timeout = null
      connected = false
      writeQueue.clear()
      pendingWrite = null
      try {
        gatt?.disconnect()
      } catch (_: Exception) {
      }
      try {
        gatt?.close()
      } catch (_: Exception) {
      }
      gatt = null
      tx = null
      rx = null
    }

    private fun drainWrites() {
      if (pendingWrite != null) return
      val next = writeQueue.poll() ?: return
      val currentGatt = gatt
      val currentTx = tx
      if (!connected || currentGatt == null || currentTx == null) {
        next.callback(false, "${side.wireName} glass is not connected")
        mainHandler.post { drainWrites() }
        return
      }

      pendingWrite = next
      val accepted = try {
        currentTx.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
          currentGatt.writeCharacteristic(
            currentTx,
            next.data,
            BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT,
          ) == GATT_API_SUCCESS
        } else {
          @Suppress("DEPRECATION")
          run {
            currentTx.value = next.data
            currentGatt.writeCharacteristic(currentTx)
          }
        }
      } catch (ex: Exception) {
        false
      }

      if (!accepted) {
        pendingWrite = null
        next.callback(false, "Android rejected ${side.wireName} G1 GATT write")
        mainHandler.post { drainWrites() }
      }
    }
  }

  private val mainHandler = Handler(Looper.getMainLooper())
  private val scanSettings = ScanSettings.Builder()
    .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
    .build()
  private val connections = EnumMapCompat<Side, GlassConnection>()
  private val reconnectAttempts = EnumMapCompat<Side, Int>()
  private val reconnectRunnables = EnumMapCompat<Side, Runnable>()

  private var scanCallback: ScanCallback? = null
  private var scanTimeout: Runnable? = null
  private var scanning = false
  private var connectingPair = false
  private var shouldMaintainConnection = false
  private var pendingConnectInvoke: Invoke? = null
  private var heartbeatRunnable: Runnable? = null
  private var heartbeatSeq = 0
  private var leftBattery: BatteryInfo? = null
  private var rightBattery: BatteryInfo? = null
  private var batteryLastUpdated: String? = null
  private var micRecording = false
  private var micSeqAdd = 0
  private val micChunks = TreeMap<Int, ByteArray>()
  private var lastEvent: String? = null
  private var lastError: String? = null

  init {
    activePlugin = this
  }

  @Command
  fun status(invoke: Invoke) {
    invoke.resolve(statusObject())
  }

  @Command
  fun scanAndConnect(invoke: Invoke) {
    mainHandler.post {
      if (!ensureBluetoothReady(invoke)) return@post
      if (pendingConnectInvoke != null || scanning || connectingPair) {
        invoke.reject("G1 scan or connection is already in progress")
        return@post
      }

      disconnectInternal(clearMessage = false)
      shouldMaintainConnection = true
      pendingConnectInvoke = invoke
      scanning = true
      connectingPair = false
      lastEvent = "Scanning for Even Realities G1 glasses"
      lastError = null

      val scanner = bluetoothAdapter()?.bluetoothLeScanner
      if (scanner == null) {
        failPendingConnect("Bluetooth LE scanner is unavailable")
        return@post
      }

      val callback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
          handleScanResult(result)
        }

        override fun onBatchScanResults(results: MutableList<ScanResult>) {
          results.forEach { handleScanResult(it) }
        }

        override fun onScanFailed(errorCode: Int) {
          failPendingConnect("G1 scan failed with Android error code $errorCode")
        }
      }
      scanCallback = callback

      try {
        scanner.startScan(null, scanSettings, callback)
      } catch (ex: Exception) {
        failPendingConnect("Unable to start G1 scan: ${ex.message ?: ex.javaClass.simpleName}")
        return@post
      }

      scanTimeout = Runnable {
        if (pendingConnectInvoke != null) {
          scanning = false
          stopScanOnly()
          lastError = if (connections[Side.LEFT]?.connected == true ||
            connections[Side.RIGHT]?.connected == true
          ) {
            "Timed out before both G1 lenses connected"
          } else {
            "No paired G1 glasses found during scan"
          }
          resolvePendingConnect()
        }
      }
      mainHandler.postDelayed(scanTimeout!!, SCAN_TIMEOUT_MS)
    }
  }

  @Command
  fun reconnectSaved(invoke: Invoke) {
    mainHandler.post {
      if (!ensureBluetoothReady(invoke)) return@post
      if (pendingConnectInvoke != null || scanning || connectingPair) {
        invoke.reject("G1 scan or connection is already in progress")
        return@post
      }

      disconnectInternal(clearMessage = false)
      shouldMaintainConnection = true
      pendingConnectInvoke = invoke
      scanning = false
      connectingPair = true
      lastEvent = "Reconnecting to saved G1 glasses"
      lastError = null

      val args = invoke.getArgs()
      val leftId = args.getString("left_device_id", null)
      val rightId = args.getString("right_device_id", null)
      val leftName = args.getString("left_device_name", "Left G1") ?: "Left G1"
      val rightName = args.getString("right_device_name", "Right G1") ?: "Right G1"
      val adapter = bluetoothAdapter()

      if (adapter == null || leftId.isNullOrBlank() || rightId.isNullOrBlank()) {
        pendingConnectInvoke = null
        connectingPair = false
        scanAndConnect(invoke)
        return@post
      }

      try {
        connectDevice(Side.LEFT, adapter.getRemoteDevice(leftId), leftName)
        connectDevice(Side.RIGHT, adapter.getRemoteDevice(rightId), rightName)
      } catch (ex: Exception) {
        failPendingConnect("Unable to reconnect saved G1 glasses: ${ex.message ?: ex.javaClass.simpleName}")
      }
    }
  }

  @Command
  fun disconnect(invoke: Invoke) {
    mainHandler.post {
      pendingConnectInvoke?.reject("G1 connection cancelled")
      pendingConnectInvoke = null
      stopScanOnly()
      disconnectInternal(clearMessage = true)
      emitStatusEvent()
      invoke.resolve(statusObject())
    }
  }

  @Command
  fun setLastEvent(invoke: Invoke) {
    val message = invoke.getArgs().getString("message", null)
    if (!message.isNullOrBlank()) {
      lastEvent = message
      lastError = null
      emitStatusEvent()
    }
    invoke.resolve(statusObject())
  }

  @Command
  fun startMicCapture(invoke: Invoke) {
    mainHandler.post {
      val right = connections[Side.RIGHT]
      if (right?.connected != true) {
        invoke.reject("Right G1 glass is not connected")
        return@post
      }

      resetMicCapture()
      micRecording = true
      right.enqueueWrite(byteArrayOf(0x0E, 0x01)) { ok, message ->
        if (ok) {
          lastEvent = "G1 microphone opened"
          lastError = null
          emitStatusEvent()
          invoke.resolve(statusObject())
        } else {
          micRecording = false
          val error = message ?: "Unable to open G1 microphone"
          lastError = error
          invoke.reject(error)
        }
      }
    }
  }

  @Command
  fun stopMicCapture(invoke: Invoke) {
    mainHandler.post {
      micRecording = false
      val capture = takeMicCapture()
      val right = connections[Side.RIGHT]

      fun resolveCapture() {
        invoke.resolve(
          JSObject()
            .put("audio_base64", Base64.encodeToString(capture.first, Base64.NO_WRAP))
            .put("chunk_count", capture.second),
        )
      }

      if (right?.connected == true) {
        right.enqueueWrite(byteArrayOf(0x0E, 0x00)) { _, _ ->
          lastEvent = "G1 microphone closed"
          lastError = null
          emitStatusEvent()
          resolveCapture()
        }
      } else {
        resolveCapture()
      }
    }
  }

  @Command
  fun writePackets(invoke: Invoke) {
    mainHandler.post {
      val args = invoke.getArgs()
      val side = (args.getString("side", "both") ?: "both").lowercase(Locale.US)
      val packetsJson = args.optJSONArray("packets_base64")
      val delayMs = args.optLong("delay_ms", 100L).coerceAtLeast(0L)
      val finalEvent = args.getString("final_event", "Sent G1 command") ?: "Sent G1 command"
      if (packetsJson == null || packetsJson.length() == 0) {
        invoke.resolve(statusObject())
        return@post
      }

      val packets = mutableListOf<ByteArray>()
      try {
        for (i in 0 until packetsJson.length()) {
          packets.add(Base64.decode(packetsJson.getString(i), Base64.DEFAULT))
        }
      } catch (ex: Exception) {
        invoke.reject("Invalid G1 packet payload: ${ex.message ?: ex.javaClass.simpleName}")
        return@post
      }

      val targets = selectedConnections(side)
      if (targets.isEmpty() || targets.any { !it.connected }) {
        invoke.reject("G1 glasses are not connected")
        return@post
      }

      var remaining = packets.size * targets.size
      var failedMessage: String? = null

      fun complete(ok: Boolean, message: String?) {
        if (!ok && failedMessage == null) failedMessage = message ?: "G1 write failed"
        remaining -= 1
        if (remaining == 0) {
          val error = failedMessage
          if (error != null) {
            lastError = error
            invoke.reject(error)
          } else {
            lastEvent = finalEvent
            lastError = null
            emitStatusEvent()
            invoke.resolve(statusObject())
          }
        }
      }

      packets.forEachIndexed { index, packet ->
        mainHandler.postDelayed({
          targets.forEach { connection ->
            connection.enqueueWrite(packet) { ok, message -> complete(ok, message) }
          }
        }, delayMs * index)
      }
    }
  }

  override fun onDestroy(activity: AppCompatActivity) {
    disconnectInternal(clearMessage = false)
    if (activePlugin === this) {
      activePlugin = null
    }
    super.onDestroy(activity)
  }

  private fun handleScanResult(result: ScanResult) {
    if (pendingConnectInvoke == null) return
    val name = scanResultName(result)
    if (name.isBlank()) return
    val parsed = parseG1Name(name) ?: return
    val (_, side) = parsed
    if (connections[side] != null) {
      return
    }
    lastEvent = "${side.wireName} G1 found: $name; connecting"
    lastError = null
    emitStatusEvent()
    connectDevice(side, result.device, name)
  }

  private fun connectDevice(side: Side, device: BluetoothDevice, displayName: String) {
    cancelReconnect(side)
    val name = safeDeviceName(device) ?: displayName
    val connection = GlassConnection(side, name, safeDeviceAddress(device), device)
    connections[side]?.close()
    connections[side] = connection

    val callback = object : BluetoothGattCallback() {
      override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
        if (newState == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS) {
          mainHandler.post {
            lastEvent = "${side.wireName} G1 connected; discovering services"
            try {
              gatt.discoverServices()
            } catch (ex: Exception) {
              failConnection(connection, "Service discovery failed: ${ex.message ?: ex.javaClass.simpleName}")
            }
          }
        } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
          mainHandler.post {
            val wasReady = connection.connected
            connection.connected = false
            connection.close()
            if (connections[side] === connection) {
              connections.remove(side)
            }
            lastEvent = if (wasReady) {
              "${side.wireName} G1 disconnected"
            } else {
              "${side.wireName} G1 disconnected during connection"
            }
            if (!wasReady && pendingConnectInvoke != null) {
              lastError = "${side.wireName} G1 disconnected during connection (status $status)"
            }
            emitStatusEvent()
            if (wasReady && shouldMaintainConnection) {
              scheduleReconnect(side, connection.device, connection.name)
            }
          }
        }
      }

      override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
        mainHandler.post {
          if (status != BluetoothGatt.GATT_SUCCESS) {
            failConnection(connection, "G1 service discovery failed with status $status")
            return@post
          }
          val service = gatt.getService(UART_SERVICE_UUID)
          val rx = service?.getCharacteristic(UART_RX_CHAR_UUID)
          val tx = service?.getCharacteristic(UART_TX_CHAR_UUID)
          if (service == null || rx == null || tx == null) {
            failConnection(connection, "G1 UART service was not found")
            return@post
          }

          connection.gatt = gatt
          connection.rx = rx
          connection.tx = tx
          connection.name = safeDeviceName(device) ?: connection.name

          try {
            val notificationEnabled = gatt.setCharacteristicNotification(rx, true)
            if (!notificationEnabled) {
              failConnection(connection, "${side.wireName} G1 notifications could not be enabled")
              return@post
            }
            val descriptor = rx.getDescriptor(CCCD_UUID)
            if (descriptor != null) {
              val accepted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                gatt.writeDescriptor(
                  descriptor,
                  BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE,
                ) == GATT_API_SUCCESS
              } else {
                @Suppress("DEPRECATION")
                run {
                  descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                  gatt.writeDescriptor(descriptor)
                }
              }
              if (!accepted) {
                failConnection(connection, "${side.wireName} G1 notification descriptor write was rejected")
                return@post
              }
            } else {
              finishConnectionSetup(connection, gatt)
            }
          } catch (ex: Exception) {
            failConnection(connection, "${side.wireName} G1 notification setup failed: ${ex.message ?: ex.javaClass.simpleName}")
          }
        }
      }

      override fun onDescriptorWrite(
        gatt: BluetoothGatt,
        descriptor: BluetoothGattDescriptor,
        status: Int,
      ) {
        if (descriptor.uuid != CCCD_UUID) return
        mainHandler.post {
          if (status == BluetoothGatt.GATT_SUCCESS) {
            finishConnectionSetup(connection, gatt)
          } else {
            failConnection(connection, "${side.wireName} G1 notification descriptor failed with status $status")
          }
        }
      }

      override fun onCharacteristicWrite(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        status: Int,
      ) {
        connection.handleWrite(status)
      }

      @Deprecated("Deprecated in Android 13")
      override fun onCharacteristicChanged(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
      ) {
        @Suppress("DEPRECATION")
        handleNotification(connection.side, characteristic.value ?: return)
      }

      override fun onCharacteristicChanged(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        value: ByteArray,
      ) {
        handleNotification(connection.side, value)
      }
    }

    connection.timeout = Runnable {
      if (!connection.connected) {
        failConnection(connection, "${side.wireName} G1 connection timed out")
      }
    }
    mainHandler.postDelayed(connection.timeout!!, CONNECT_TIMEOUT_MS)

    try {
      connection.gatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
        device.connectGatt(activity, false, callback, BluetoothDevice.TRANSPORT_LE)
      } else {
        @Suppress("DEPRECATION")
        device.connectGatt(activity, false, callback)
      }
    } catch (ex: Exception) {
      failConnection(connection, "Unable to connect ${side.wireName} G1: ${ex.message ?: ex.javaClass.simpleName}")
    }
  }

  private fun checkConnectComplete() {
    val leftReady = connections[Side.LEFT]?.connected == true
    val rightReady = connections[Side.RIGHT]?.connected == true
    if (leftReady && rightReady) {
      scanning = false
      connectingPair = false
      stopScanOnly()
      lastEvent = "G1 glasses connected"
      lastError = null
      startKeepAliveService()
      emitStatusEvent()
      resolvePendingConnect()
    }
  }

  private fun finishConnectionSetup(connection: GlassConnection, gatt: BluetoothGatt) {
    if (connections[connection.side] !== connection || connection.connected) {
      return
    }

    connection.timeout?.let { mainHandler.removeCallbacks(it) }
    connection.timeout = null

    try {
      gatt.requestMtu(251)
      gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
    } catch (ex: Exception) {
      lastError = "G1 setup warning: ${ex.message ?: ex.javaClass.simpleName}"
    }

    connection.connected = true
    reconnectAttempts.remove(connection.side)
    lastEvent = "${connection.side.wireName} G1 ready"
    lastError = null
    scheduleBatteryRequests(connection)
    sendHeartbeatNow()
    startHeartbeat()
    startKeepAliveService()
    emitStatusEvent()
    checkConnectComplete()
  }

  private fun failConnection(connection: GlassConnection, message: String) {
    val shouldRetry = shouldMaintainConnection && pendingConnectInvoke == null && !scanning
    connection.close()
    if (connections[connection.side] === connection) {
      connections.remove(connection.side)
    }
    lastError = message
    emitStatusEvent()
    if (pendingConnectInvoke != null && !scanning) {
      connectingPair = false
      resolvePendingConnect()
    }
    if (shouldRetry) {
      scheduleReconnect(connection.side, connection.device, connection.name)
    }
  }

  private fun failPendingConnect(message: String) {
    scanning = false
    connectingPair = false
    stopScanOnly()
    lastError = message
    emitStatusEvent()
    val invoke = pendingConnectInvoke
    pendingConnectInvoke = null
    if (invoke != null) {
      invoke.reject(message)
    }
    if (connections.values.none { it.connected }) {
      shouldMaintainConnection = false
      stopKeepAliveService()
    }
  }

  private fun resolvePendingConnect() {
    val invoke = pendingConnectInvoke ?: return
    pendingConnectInvoke = null
    invoke.resolve(statusObject())
  }

  private fun selectedConnections(side: String): List<GlassConnection> {
    return when (side) {
      "left" -> listOfNotNull(connections[Side.LEFT])
      "right" -> listOfNotNull(connections[Side.RIGHT])
      else -> listOfNotNull(connections[Side.LEFT], connections[Side.RIGHT])
    }
  }

  private fun disconnectInternal(clearMessage: Boolean) {
    shouldMaintainConnection = false
    cancelReconnects()
    stopKeepAliveService()
    stopHeartbeat()
    connections.values.toList().forEach { it.close() }
    connections.clear()
    leftBattery = null
    rightBattery = null
    batteryLastUpdated = null
    micRecording = false
    resetMicCapture()
    connectingPair = false
    if (clearMessage) {
      lastEvent = "G1 glasses disconnected"
      lastError = null
    }
  }

  private fun stopScanOnly() {
    scanTimeout?.let { mainHandler.removeCallbacks(it) }
    scanTimeout = null
    val callback = scanCallback
    val scanner = bluetoothAdapter()?.bluetoothLeScanner
    if (callback != null && scanner != null) {
      try {
        scanner.stopScan(callback)
      } catch (_: Exception) {
      }
    }
    scanCallback = null
    scanning = false
  }

  private fun startHeartbeat() {
    if (heartbeatRunnable != null) return
    heartbeatRunnable = object : Runnable {
      override fun run() {
        val packet = buildHeartbeat()
        connections.values
          .filter { it.connected }
          .forEach { it.enqueueWrite(packet) { _, _ -> } }
        mainHandler.postDelayed(this, HEARTBEAT_MS)
      }
    }
    mainHandler.postDelayed(heartbeatRunnable!!, HEARTBEAT_MS)
  }

  private fun stopHeartbeat() {
    heartbeatRunnable?.let { mainHandler.removeCallbacks(it) }
    heartbeatRunnable = null
  }

  private fun sendHeartbeatNow(): Boolean {
    val packet = buildHeartbeat()
    var sent = false
    connections.values
      .filter { it.connected }
      .forEach { connection ->
        sent = true
        connection.enqueueWrite(packet) { ok, message ->
          if (!ok && message != null) {
            lastError = message
            emitStatusEvent()
          }
        }
      }
    return sent
  }

  private fun scheduleReconnect(side: Side, device: BluetoothDevice, displayName: String) {
    if (!shouldMaintainConnection || reconnectRunnables[side] != null) return
    if (connections[side]?.connected == true) return

    val nextAttempt = (reconnectAttempts[side] ?: 0) + 1
    if (nextAttempt > MAX_RECONNECT_ATTEMPTS) {
      lastError = "${side.wireName} G1 reconnect gave up after $MAX_RECONNECT_ATTEMPTS attempts"
      emitStatusEvent()
      return
    }

    reconnectAttempts[side] = nextAttempt
    val delayMs = reconnectDelayMs(nextAttempt)
    lastEvent = "${side.wireName} G1 reconnect attempt $nextAttempt scheduled"
    lastError = null
    emitStatusEvent()

    val runnable = Runnable {
      reconnectRunnables.remove(side)
      if (!shouldMaintainConnection || connections[side]?.connected == true) return@Runnable
      lastEvent = "Reconnecting ${side.wireName} G1"
      lastError = null
      emitStatusEvent()
      connectDevice(side, device, displayName)
    }
    reconnectRunnables[side] = runnable
    mainHandler.postDelayed(runnable, delayMs)
  }

  private fun reconnectDelayMs(attempt: Int): Long {
    val seconds = when (attempt) {
      1 -> 2
      2 -> 4
      3 -> 8
      4 -> 16
      else -> 30
    }
    return seconds * 1_000L
  }

  private fun cancelReconnect(side: Side) {
    reconnectRunnables.remove(side)?.let { mainHandler.removeCallbacks(it) }
  }

  private fun cancelReconnects() {
    reconnectRunnables.values.toList().forEach { mainHandler.removeCallbacks(it) }
    reconnectRunnables.clear()
    reconnectAttempts.clear()
  }

  private fun startKeepAliveService() {
    try {
      G1KeepAliveService.start(activity.applicationContext)
    } catch (ex: Exception) {
      lastError = "G1 keep-alive service could not start: ${ex.message ?: ex.javaClass.simpleName}"
    }
  }

  private fun stopKeepAliveService() {
    try {
      G1KeepAliveService.stop(activity.applicationContext)
    } catch (_: Exception) {
    }
  }

  private fun serviceKeepAliveTick(): G1KeepAliveSnapshot {
    if (shouldMaintainConnection) {
      sendHeartbeatNow()
    }
    return G1KeepAliveSnapshot(
      maintaining = shouldMaintainConnection,
      leftConnected = connections[Side.LEFT]?.connected == true,
      rightConnected = connections[Side.RIGHT]?.connected == true,
      lastEvent = lastEvent,
      lastError = lastError,
    )
  }

  private fun buildHeartbeat(): ByteArray {
    val seq = (heartbeatSeq % 0xFF).toByte()
    heartbeatSeq += 1
    return byteArrayOf(0x25, 0x06, 0x00, seq, 0x04, seq)
  }

  private fun scheduleBatteryRequests(connection: GlassConnection) {
    mainHandler.postDelayed({
      if (connection.connected) {
        connection.enqueueWrite(byteArrayOf(0x2C, 0x01)) { _, _ -> }
      }
    }, 500)
    mainHandler.postDelayed({
      if (connection.connected) {
        connection.enqueueWrite(byteArrayOf(0x2C, 0x01)) { _, _ -> }
      }
    }, 2_000)
  }

  private fun handleNotification(side: Side, data: ByteArray) {
    if (data.isEmpty()) return
    mainHandler.post {
      when (data[0].toInt() and 0xFF) {
        0x2C -> {
          if (data.size >= 3) {
            val timestamp = timestamp()
            val battery = BatteryInfo(
              side = side,
              percentage = (data[2].toInt() and 0xFF).coerceAtMost(100),
              voltage = data.getOrNull(3)?.toInt()?.and(0xFF) ?: 0,
              isCharging = (data.getOrNull(4)?.toInt()?.and(0x01) ?: 0) == 1,
              timestamp = timestamp,
            )
            if (side == Side.LEFT) leftBattery = battery else rightBattery = battery
            batteryLastUpdated = timestamp
            lastEvent = "${side.wireName} G1 battery: ${battery.percentage}%"
            lastError = null
            emitBatteryEvent(battery)
          }
        }
        0x23 -> {
          lastEvent = "${side.wireName} G1 side button pressed"
          emitButtonEvent(side, "button_press", null, "G1 side button pressed")
        }
        0xF5 -> {
          val subcommand = data.getOrNull(1)?.toInt()?.and(0xFF)
          val action = when {
            subcommand == 0x00 -> "exit_dashboard"
            side == Side.LEFT && subcommand == 0x17 -> "voice_start"
            side == Side.LEFT && subcommand == 0x18 -> "voice_stop"
            side == Side.RIGHT && subcommand == 0x17 -> "conversation_toggle"
            side == Side.RIGHT && subcommand == 0x18 -> "conversation_release"
            side == Side.LEFT && subcommand == 0x01 -> "page_up"
            side == Side.RIGHT && subcommand == 0x01 -> "page_down"
            else -> "state_change"
          }
          lastEvent = "${side.wireName} G1 ${action.replace('_', ' ')}"
          emitButtonEvent(side, action, subcommand, "G1 ${side.wireName} event $subcommand")
        }
        0x0E -> {
          val action = if ((data.getOrNull(2)?.toInt()?.and(0xFF) ?: 0) == 1) "opened" else "closed"
          lastEvent = "${side.wireName} G1 microphone $action"
          trigger(
            "g1-event",
            JSObject()
              .put("type", "microphone")
              .put("side", side.wireName)
              .put("action", action)
              .put("subcommand", data.getOrNull(1)?.toInt()?.and(0xFF)),
          )
        }
        0xF1 -> {
          handleMicData(data)
        }
      }
    }
  }

  private fun handleMicData(data: ByteArray) {
    if (!micRecording || data.size < 3) return
    val seq = data[1].toInt() and 0xFF
    if (seq == 255) {
      micSeqAdd += 255
    }
    micChunks[micSeqAdd + seq] = data.copyOfRange(2, data.size)
  }

  private fun resetMicCapture() {
    micSeqAdd = 0
    micChunks.clear()
  }

  private fun takeMicCapture(): Pair<ByteArray, Int> {
    val count = micChunks.size
    val out = ByteArrayOutputStream()
    micChunks.values.forEach { out.write(it) }
    resetMicCapture()
    return out.toByteArray() to count
  }

  private fun emitStatusEvent() {
    trigger(
      "g1-event",
      JSObject()
        .put("type", "status")
        .put("status", statusObject()),
    )
  }

  private fun emitBatteryEvent(battery: BatteryInfo) {
    trigger(
      "g1-event",
      JSObject()
        .put("type", "battery")
        .put("side", battery.side.wireName)
        .put("battery", battery.toJson())
        .put("status", statusObject()),
    )
  }

  private fun emitButtonEvent(side: Side, action: String, subcommand: Int?, message: String) {
    trigger(
      "g1-event",
      JSObject()
        .put("type", "button")
        .put("side", side.wireName)
        .put("action", action)
        .put("subcommand", subcommand)
        .put("message", message),
    )
  }

  private fun statusObject(): JSObject {
    val left = connections[Side.LEFT]
    val right = connections[Side.RIGHT]
    val battery = JSObject()
      .put("left", leftBattery?.toJson() ?: org.json.JSONObject.NULL)
      .put("right", rightBattery?.toJson() ?: org.json.JSONObject.NULL)
      .put("last_updated", batteryLastUpdated)

    return JSObject()
      .put("supported", bluetoothAdapter() != null)
      .put("scanning", scanning)
      .put("connected", left?.connected == true && right?.connected == true)
      .put("left", left?.summary() ?: org.json.JSONObject.NULL)
      .put("right", right?.summary() ?: org.json.JSONObject.NULL)
      .put("battery", battery)
      .put("last_event", lastEvent)
      .put("last_error", lastError)
  }

  private fun ensureBluetoothReady(invoke: Invoke): Boolean {
    val adapter = bluetoothAdapter()
    if (adapter == null) {
      invoke.reject("Bluetooth is not available on this Android device")
      return false
    }
    val missing = missingBluetoothPermissions()
    if (missing.isNotEmpty()) {
      ActivityCompat.requestPermissions(activity, missing, G1_PERMISSION_REQUEST_CODE)
      invoke.reject("Bluetooth and location permissions are required for G1 glasses. Grant the Android permissions and tap Connect again.")
      return false
    }
    if (!adapter.isEnabled) {
      invoke.reject("Bluetooth is turned off")
      return false
    }
    return true
  }

  private fun missingBluetoothPermissions(): Array<String> {
    val permissions = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
      arrayOf(
        Manifest.permission.BLUETOOTH_SCAN,
        Manifest.permission.BLUETOOTH_CONNECT,
        Manifest.permission.ACCESS_FINE_LOCATION,
      )
    } else {
      arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }
    return permissions.filter {
      ContextCompat.checkSelfPermission(activity, it) != PackageManager.PERMISSION_GRANTED
    }.toTypedArray()
  }

  private fun bluetoothAdapter(): BluetoothAdapter? {
    return try {
      val manager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
        activity.getSystemService(AndroidBluetoothManager::class.java)
      } else {
        @Suppress("DEPRECATION")
        activity.getSystemService(Context.BLUETOOTH_SERVICE) as AndroidBluetoothManager
      }
      manager?.adapter
    } catch (_: Exception) {
      null
    }
  }

  private fun scanResultName(result: ScanResult): String {
    return result.scanRecord?.deviceName
      ?: safeDeviceName(result.device)
      ?: ""
  }

  private fun safeDeviceName(device: BluetoothDevice): String? {
    return try {
      device.name
    } catch (_: Exception) {
      null
    }
  }

  private fun safeDeviceAddress(device: BluetoothDevice): String {
    return try {
      device.address
    } catch (_: Exception) {
      ""
    }
  }

  private fun parseG1Name(name: String): Pair<String, Side>? {
    val parts = name.split("_")
    if (parts.size >= 4 && parts[0].startsWith("G", ignoreCase = true)) {
      val side = when (parts[2].uppercase(Locale.US)) {
        "L" -> Side.LEFT
        "R" -> Side.RIGHT
        else -> null
      }
      if (side != null) return parts[1] to side
    }
    return when {
      name.contains("_L_") -> "default" to Side.LEFT
      name.contains("_R_") -> "default" to Side.RIGHT
      else -> null
    }
  }

  private fun timestamp(): String {
    val formatter = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
    formatter.timeZone = TimeZone.getTimeZone("UTC")
    return formatter.format(Date())
  }

  private class EnumMapCompat<K : Enum<K>, V> {
    private val backing = LinkedHashMap<K, V>()

    operator fun get(key: K): V? = backing[key]
    operator fun set(key: K, value: V) {
      backing[key] = value
    }
    fun remove(key: K): V? = backing.remove(key)
    fun clear() = backing.clear()
    val values: Collection<V>
      get() = backing.values
  }

  companion object {
    @Volatile
    private var activePlugin: G1Plugin? = null

    private val UART_SERVICE_UUID: UUID = UUID.fromString("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
    private val UART_TX_CHAR_UUID: UUID = UUID.fromString("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
    private val UART_RX_CHAR_UUID: UUID = UUID.fromString("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
    private val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
    private const val SCAN_TIMEOUT_MS = 30_000L
    private const val CONNECT_TIMEOUT_MS = 20_000L
    private const val HEARTBEAT_MS = 5_000L
    private const val MAX_RECONNECT_ATTEMPTS = 50
    private const val G1_PERMISSION_REQUEST_CODE = 7438
    private const val GATT_API_SUCCESS = 0

    internal fun keepAliveFromService(): G1KeepAliveSnapshot {
      return activePlugin?.serviceKeepAliveTick() ?: G1KeepAliveSnapshot(
        maintaining = false,
        leftConnected = false,
        rightConnected = false,
        lastEvent = "G1 bridge is not active",
        lastError = null,
      )
    }
  }
}

class G1KeepAliveService : Service() {
  private val handler = Handler(Looper.getMainLooper())
  private var wakeLock: PowerManager.WakeLock? = null

  private val tickRunnable = object : Runnable {
    override fun run() {
      val snapshot = G1Plugin.keepAliveFromService()
      if (!snapshot.maintaining && !snapshot.leftConnected && !snapshot.rightConnected) {
        stopSelf()
        return
      }

      refreshWakeLock()
      updateNotification(snapshot)
      handler.postDelayed(this, TICK_MS)
    }
  }

  override fun onCreate() {
    super.onCreate()
    createNotificationChannel()
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    if (intent?.action == ACTION_STOP) {
      stopSelf()
      return START_NOT_STICKY
    }

    val snapshot = G1Plugin.keepAliveFromService()
    startForegroundCompat(buildNotification(snapshot))
    refreshWakeLock()
    handler.removeCallbacks(tickRunnable)
    handler.postDelayed(tickRunnable, TICK_MS)
    return START_STICKY
  }

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onDestroy() {
    handler.removeCallbacks(tickRunnable)
    releaseWakeLock()
    super.onDestroy()
  }

  private fun startForegroundCompat(notification: Notification) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
      startForeground(
        NOTIFICATION_ID,
        notification,
        ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
      )
    } else {
      startForeground(NOTIFICATION_ID, notification)
    }
  }

  private fun updateNotification(snapshot: G1KeepAliveSnapshot) {
    val manager = getSystemService(NotificationManager::class.java) ?: return
    manager.notify(NOTIFICATION_ID, buildNotification(snapshot))
  }

  private fun buildNotification(snapshot: G1KeepAliveSnapshot): Notification {
    val status = when {
      snapshot.leftConnected && snapshot.rightConnected -> "Connected to glasses"
      snapshot.leftConnected || snapshot.rightConnected -> {
        val sides = listOfNotNull(
          if (snapshot.leftConnected) "L" else null,
          if (snapshot.rightConnected) "R" else null,
        ).joinToString("")
        "Partially connected ($sides)"
      }
      snapshot.maintaining -> "Disconnected - trying to reconnect..."
      else -> snapshot.lastEvent ?: "Glasses connection idle"
    }

    val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
    val pendingIntent = launchIntent?.let {
      PendingIntent.getActivity(
        this,
        0,
        it,
        PendingIntent.FLAG_UPDATE_CURRENT or immutableFlag(),
      )
    }

    return NotificationCompat.Builder(this, CHANNEL_ID)
      .setSmallIcon(R.mipmap.ic_launcher)
      .setContentTitle("AGiXT Glasses Connection")
      .setContentText(status)
      .setOngoing(true)
      .setOnlyAlertOnce(true)
      .setShowWhen(true)
      .setCategory(NotificationCompat.CATEGORY_SERVICE)
      .setPriority(NotificationCompat.PRIORITY_MAX)
      .setContentIntent(pendingIntent)
      .build()
  }

  private fun createNotificationChannel() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
    val manager = getSystemService(NotificationManager::class.java) ?: return
    val channel = NotificationChannel(
      CHANNEL_ID,
      "AGiXT Glasses Connection",
      NotificationManager.IMPORTANCE_HIGH,
    ).apply {
      description = "Maintains connection to your glasses in the background"
      setSound(null, null)
      enableVibration(false)
      setShowBadge(false)
    }
    manager.createNotificationChannel(channel)
  }

  private fun refreshWakeLock() {
    try {
      val lock = wakeLock ?: run {
        val powerManager = getSystemService(PowerManager::class.java) ?: return
        powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "$packageName:g1_keep_alive").apply {
          setReferenceCounted(false)
          wakeLock = this
        }
      }
      lock.acquire(WAKELOCK_TIMEOUT_MS)
    } catch (_: Exception) {
    }
  }

  private fun releaseWakeLock() {
    try {
      wakeLock?.takeIf { it.isHeld }?.release()
    } catch (_: Exception) {
    } finally {
      wakeLock = null
    }
  }

  companion object {
    private const val ACTION_START = "systems.xt.agixt.desktop.g1.START_KEEP_ALIVE"
    private const val ACTION_STOP = "systems.xt.agixt.desktop.g1.STOP_KEEP_ALIVE"
    private const val CHANNEL_ID = "agixt_g1_keep_alive"
    private const val NOTIFICATION_ID = 7438
    private const val TICK_MS = 15_000L
    private const val WAKELOCK_TIMEOUT_MS = 45_000L

    fun start(context: Context) {
      val intent = Intent(context, G1KeepAliveService::class.java).setAction(ACTION_START)
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        ContextCompat.startForegroundService(context, intent)
      } else {
        context.startService(intent)
      }
    }

    fun stop(context: Context) {
      val intent = Intent(context, G1KeepAliveService::class.java).setAction(ACTION_STOP)
      try {
        context.startService(intent)
      } catch (_: Exception) {
        context.stopService(Intent(context, G1KeepAliveService::class.java))
      }
    }

    private fun immutableFlag(): Int {
      return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
        PendingIntent.FLAG_IMMUTABLE
      } else {
        0
      }
    }
  }
}
