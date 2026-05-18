package systems.xt.agixt.desktop

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.enableEdgeToEdge
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : TauriActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
    window.decorView.post { requestAgixtRuntimePermissions() }
  }

  private fun requestAgixtRuntimePermissions() {
    val permissions = LinkedHashSet<String>()

    addPermissionIfNeeded(permissions, Manifest.permission.ACCESS_FINE_LOCATION)
    addPermissionIfNeeded(permissions, Manifest.permission.ACCESS_COARSE_LOCATION)

    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
      addPermissionIfNeeded(permissions, Manifest.permission.BLUETOOTH_SCAN)
      addPermissionIfNeeded(permissions, Manifest.permission.BLUETOOTH_CONNECT)
    }

    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      addPermissionIfNeeded(permissions, Manifest.permission.POST_NOTIFICATIONS)
      addPermissionIfNeeded(permissions, Manifest.permission.READ_MEDIA_IMAGES)
      addPermissionIfNeeded(permissions, Manifest.permission.READ_MEDIA_VIDEO)
      addPermissionIfNeeded(permissions, Manifest.permission.READ_MEDIA_AUDIO)
    } else {
      addPermissionIfNeeded(permissions, Manifest.permission.READ_EXTERNAL_STORAGE)
      addPermissionIfNeeded(permissions, Manifest.permission.WRITE_EXTERNAL_STORAGE)
    }

    addPermissionIfNeeded(permissions, Manifest.permission.READ_CALENDAR)
    addPermissionIfNeeded(permissions, Manifest.permission.WRITE_CALENDAR)
    addPermissionIfNeeded(permissions, Manifest.permission.RECORD_AUDIO)
    addPermissionIfNeeded(permissions, Manifest.permission.READ_CONTACTS)
    addPermissionIfNeeded(permissions, Manifest.permission.SEND_SMS)
    addPermissionIfNeeded(permissions, Manifest.permission.CALL_PHONE)
    addPermissionIfNeeded(permissions, Manifest.permission.READ_PHONE_STATE)
    addPermissionIfNeeded(permissions, Manifest.permission.CAMERA)

    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      addPermissionIfNeeded(permissions, Manifest.permission.READ_PHONE_NUMBERS)
    }

    if (permissions.isNotEmpty()) {
      ActivityCompat.requestPermissions(
        this,
        permissions.toTypedArray(),
        AGIXT_RUNTIME_PERMISSION_REQUEST_CODE
      )
    }
  }

  private fun addPermissionIfNeeded(permissions: MutableSet<String>, permission: String) {
    if (ContextCompat.checkSelfPermission(this, permission) != PackageManager.PERMISSION_GRANTED) {
      permissions.add(permission)
    }
  }

  companion object {
    private const val AGIXT_RUNTIME_PERMISSION_REQUEST_CODE = 7437
  }
}
