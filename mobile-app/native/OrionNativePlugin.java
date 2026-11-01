package dev.kiyan.orion;

import android.app.DownloadManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Environment;
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
        String why = i != null ? i.getStringExtra("orion_reason") : null;
        if (i != null) i.removeExtra("orion_reason");
        ret.put("action", a == null ? "" : a);
        ret.put("reason", why == null ? "" : why);
        call.resolve(ret);
    }

    /** Keep the phone linked to the PC in the background (calls + find my phone with the app closed). */
    @PluginMethod
    public void startLink(PluginCall call) {
        SharedPreferences.Editor e = getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).edit();
        e.putString("addr", call.getString("addr", "")).putString("pin", call.getString("pin", "")).putBoolean("on", true).apply();
        try {
            LinkService.start(getContext());
            JSObject ret = new JSObject();
            boolean fs = true;
            if (Build.VERSION.SDK_INT >= 34) {
                android.app.NotificationManager nm = (android.app.NotificationManager) getContext().getSystemService(Context.NOTIFICATION_SERVICE);
                fs = nm.canUseFullScreenIntent();
            }
            ret.put("fullScreen", fs);
            call.resolve(ret);
        } catch (Exception ex) { call.reject(ex.getMessage()); }
    }

    /** Android 14+: let ORION's calls appear full-screen (like a real incoming call). */
    @PluginMethod
    public void openFullScreenSettings(PluginCall call) {
        try {
            Intent i = Build.VERSION.SDK_INT >= 34
                    ? new Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT, Uri.parse("package:" + getContext().getPackageName()))
                    : new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
            launch(i);
        } catch (Exception ex) { }
        call.resolve();
    }

    @PluginMethod
    public void stopLink(PluginCall call) {
        getContext().getSharedPreferences(LinkService.PREFS, Context.MODE_PRIVATE).edit().putBoolean("on", false).apply();
        getContext().stopService(new Intent(getContext(), LinkService.class));
        call.resolve();
    }

    @PluginMethod
    public void stopRing(PluginCall call) {
        Intent i = new Intent(getContext(), LinkService.class).setAction(LinkService.STOP_RING);
        try { if (Build.VERSION.SDK_INT >= 26) getContext().startForegroundService(i); else getContext().startService(i); }
        catch (Exception ignored) { }
        call.resolve();
    }

    @PluginMethod
    public void copyText(PluginCall call) {
        ClipboardManager cm = (ClipboardManager) getContext().getSystemService(Context.CLIPBOARD_SERVICE);
        cm.setPrimaryClip(ClipData.newPlainText("ORION", call.getString("text", "")));
        call.resolve();
    }

    @PluginMethod
    public void readClipboard(PluginCall call) {
        ClipboardManager cm = (ClipboardManager) getContext().getSystemService(Context.CLIPBOARD_SERVICE);
        JSObject ret = new JSObject();
        String t = "";
        try {
            ClipData d = cm.getPrimaryClip();
            if (d != null && d.getItemCount() > 0 && d.getItemAt(0).getText() != null) t = d.getItemAt(0).getText().toString();
        } catch (Exception ignored) { }
        ret.put("text", t);
        call.resolve(ret);
    }

    /** Save a file the PC sent to the phone's Downloads folder. */
    @PluginMethod
    public void download(PluginCall call) {
        try {
            String name = call.getString("name", "file");
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(call.getString("url", "")));
            r.addRequestHeader("X-PIN", call.getString("pin", ""));
            r.setTitle(name);
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "ORION/" + name);
            ((DownloadManager) getContext().getSystemService(Context.DOWNLOAD_SERVICE)).enqueue(r);
            call.resolve();
        } catch (Exception ex) { call.reject(ex.getMessage()); }
    }
}
