package dev.kiyan.orion;

import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.hardware.camera2.CameraManager;
import android.net.Uri;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.provider.AlarmClock;
import android.provider.Settings;

import androidx.core.content.ContextCompat;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.util.List;
import java.util.Locale;

/** ORION's phone powers: alarms, timers, opening apps, torch, vibration and the floating bubble. */
@CapacitorPlugin(name = "OrionNative")
public class OrionNativePlugin extends Plugin {

    private void launch(Intent i) {
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
    }

    @PluginMethod
    public void setAlarm(PluginCall call) {
        try {
            Intent i = new Intent(AlarmClock.ACTION_SET_ALARM);
            i.putExtra(AlarmClock.EXTRA_HOUR, call.getInt("hour", 7));
            i.putExtra(AlarmClock.EXTRA_MINUTES, call.getInt("minute", 0));
            i.putExtra(AlarmClock.EXTRA_MESSAGE, call.getString("message", "ORION"));
            i.putExtra(AlarmClock.EXTRA_SKIP_UI, true);
            launch(i);
            call.resolve();
        } catch (Exception e) {
            call.reject("Couldn't set the alarm: " + e.getMessage());
        }
    }

    @PluginMethod
    public void setTimer(PluginCall call) {
        try {
            Intent i = new Intent(AlarmClock.ACTION_SET_TIMER);
            i.putExtra(AlarmClock.EXTRA_LENGTH, call.getInt("seconds", 60));
            i.putExtra(AlarmClock.EXTRA_MESSAGE, call.getString("message", "ORION"));
            i.putExtra(AlarmClock.EXTRA_SKIP_UI, true);
            launch(i);
            call.resolve();
        } catch (Exception e) {
            call.reject("Couldn't set the timer: " + e.getMessage());
        }
    }

    @PluginMethod
    public void showAlarms(PluginCall call) {
        try {
            launch(new Intent(AlarmClock.ACTION_SHOW_ALARMS));
            call.resolve();
        } catch (Exception e) {
            call.reject(e.getMessage());
        }
    }

    @PluginMethod
    public void openApp(PluginCall call) {
        String want = call.getString("name", "").toLowerCase(Locale.ROOT).trim();
        PackageManager pm = getContext().getPackageManager();
        Intent main = new Intent(Intent.ACTION_MAIN);
        main.addCategory(Intent.CATEGORY_LAUNCHER);
        List<ResolveInfo> apps = pm.queryIntentActivities(main, 0);
        ResolveInfo best = null;
        int bestScore = 0;
        for (ResolveInfo r : apps) {
            String label = String.valueOf(r.loadLabel(pm)).toLowerCase(Locale.ROOT);
            int score = label.equals(want) ? 3 : label.startsWith(want) ? 2 : label.contains(want) ? 1 : 0;
            if (score > bestScore) { bestScore = score; best = r; }
        }
        if (best == null) { call.reject("No app called '" + want + "' on this phone."); return; }
        Intent i = pm.getLaunchIntentForPackage(best.activityInfo.packageName);
        if (i == null) { call.reject("That app can't be opened."); return; }
        launch(i);
        JSObject ret = new JSObject();
        ret.put("opened", String.valueOf(best.loadLabel(pm)));
        call.resolve(ret);
    }

    @PluginMethod
    public void listApps(PluginCall call) {
        PackageManager pm = getContext().getPackageManager();
        Intent main = new Intent(Intent.ACTION_MAIN);
        main.addCategory(Intent.CATEGORY_LAUNCHER);
        JSArray arr = new JSArray();
        for (ResolveInfo r : pm.queryIntentActivities(main, 0)) arr.put(String.valueOf(r.loadLabel(pm)));
        JSObject ret = new JSObject();
        ret.put("apps", arr);
        call.resolve(ret);
    }

    @PluginMethod
    public void torch(PluginCall call) {
        try {
            CameraManager cm = (CameraManager) getContext().getSystemService(Context.CAMERA_SERVICE);
            cm.setTorchMode(cm.getCameraIdList()[0], call.getBoolean("on", true));
            call.resolve();
        } catch (Exception e) {
            call.reject("Torch unavailable: " + e.getMessage());
        }
    }

    @PluginMethod
    public void vibrate(PluginCall call) {
        try {
            Vibrator v = (Vibrator) getContext().getSystemService(Context.VIBRATOR_SERVICE);
            long ms = call.getInt("ms", 400);
            if (Build.VERSION.SDK_INT >= 26) v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE));
            else v.vibrate(ms);
            call.resolve();
        } catch (Exception e) {
            call.reject(e.getMessage());
        }
    }

    // ---------------- floating bubble overlay ----------------
    @PluginMethod
    public void canOverlay(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("granted", Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(getContext()));
        call.resolve(ret);
    }

    @PluginMethod
    public void requestOverlay(PluginCall call) {
        try {
            launch(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getContext().getPackageName())));
            call.resolve();
        } catch (Exception e) {
            call.reject(e.getMessage());
        }
    }

    @PluginMethod
    public void showBubble(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(getContext())) {
            call.reject("NEEDS_PERMISSION");
            return;
        }
        ContextCompat.startForegroundService(getContext(), new Intent(getContext(), BubbleService.class));
        call.resolve();
    }

    @PluginMethod
    public void hideBubble(PluginCall call) {
        getContext().stopService(new Intent(getContext(), BubbleService.class));
        call.resolve();
    }

    /** What the app was opened for (e.g. the bubble was tapped -> "call"). Read once, then cleared. */
    @PluginMethod
    public void consumeLaunchAction(PluginCall call) {
        JSObject ret = new JSObject();
        Intent i = getActivity() != null ? getActivity().getIntent() : null;
        String a = i != null ? i.getStringExtra("orion_action") : null;
        if (i != null) i.removeExtra("orion_action");
        ret.put("action", a == null ? "" : a);
        call.resolve(ret);
    }
}
