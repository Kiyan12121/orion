package dev.kiyan.orion;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Re-links ORION to the PC after the phone restarts (only if you turned the link on). */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        if (c.getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).getBoolean("on", false)) {
            try { LinkService.start(c); } catch (Exception ignored) { }
        }
    }
}
