package systems.xt.agixt.desktop

import android.os.Bundle

class MainActivity : TauriActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    // Feature plugins request runtime permissions when invoked; keep launch lean.
    super.onCreate(savedInstanceState)
  }
}
