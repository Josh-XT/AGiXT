package systems.xt.agixt.desktop

import android.app.Activity
import androidx.annotation.Keep
import app.tauri.annotation.Command
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin

@Keep
@TauriPlugin
class G1Plugin(private val activity: Activity) : Plugin(activity) {
    private val unsupportedMessage = "Even Realities G1 Android bridge is not available in this build"

    @Keep
    @Command
    fun status(invoke: Invoke) {
        val battery = JSObject()
        battery.put("left", null)
        battery.put("right", null)
        battery.put("last_updated", null)

        val status = JSObject()
        status.put("supported", false)
        status.put("scanning", false)
        status.put("connected", false)
        status.put("left", null)
        status.put("right", null)
        status.put("battery", battery)
        status.put("last_event", null)
        status.put("last_error", unsupportedMessage)
        invoke.resolve(status)
    }

    @Keep
    @Command
    fun scanAndConnect(invoke: Invoke) = rejectUnsupported(invoke)

    @Keep
    @Command
    fun reconnectSaved(invoke: Invoke) = rejectUnsupported(invoke)

    @Keep
    @Command
    fun disconnect(invoke: Invoke) = rejectUnsupported(invoke)

    @Keep
    @Command
    fun writePackets(invoke: Invoke) = rejectUnsupported(invoke)

    @Keep
    @Command
    fun setLastEvent(invoke: Invoke) = rejectUnsupported(invoke)

    @Keep
    @Command
    fun startMicCapture(invoke: Invoke) = rejectUnsupported(invoke)

    @Keep
    @Command
    fun stopMicCapture(invoke: Invoke) = rejectUnsupported(invoke)

    private fun rejectUnsupported(invoke: Invoke) {
        invoke.reject(unsupportedMessage)
    }
}
