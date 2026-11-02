package dev.kiyan.orion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * Live Updates: an ongoing notification that Android 16 / One UI 8 promotes to the status-bar chip and the
 * S23's Now Bar on the lock screen (ride ETA, ORION on a call…). On older phones it's a normal ongoing
 * notification. The newer APIs are reached by reflection so this still builds against older SDKs.
 */
public class NowBar {
    static final String CH = "orion_live";
    static final int ID = 77;

    static void channel(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm.getNotificationChannel(CH) != null) return;
        NotificationChannel ch = new NotificationChannel(CH, "ORION live (Now Bar)", NotificationManager.IMPORTANCE_DEFAULT);
        ch.setSound(null, null);
        ch.enableVibration(false);
        ch.setShowBadge(false);
        nm.createNotificationChannel(ch);
    }

    /** progress/max < 0 → no bar. chip = the short text in the status-bar pill (e.g. "6 min"). */
    static void post(Context c, String title, String text, String chip, int progress, int max, String action) {
        try {
            channel(c);
            Intent i = new Intent(c, MainActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            if (action != null && !action.isEmpty()) i.putExtra("orion_action", action);
            PendingIntent pi = PendingIntent.getActivity(c, 7701, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CH) : new Notification.Builder(c);
            b.setSmallIcon(android.R.drawable.ic_menu_mylocation).setContentTitle(title).setContentText(text)
                    .setOngoing(true).setOnlyAlertOnce(true).setShowWhen(false).setContentIntent(pi)
                    .setCategory(Notification.CATEGORY_PROGRESS).setVisibility(Notification.VISIBILITY_PUBLIC);
            if (max > 0 && progress >= 0) b.setProgress(max, Math.min(progress, max), false);
            android.os.Bundle ex = new android.os.Bundle();
            ex.putBoolean("android.requestPromotedOngoing", true);          // Android 16 Live Updates
            if (chip != null) ex.putString("android.shortCriticalText", chip);
            b.addExtras(ex);
            try { b.getClass().getMethod("setRequestPromotedOngoing", boolean.class).invoke(b, true); } catch (Exception ignored) { }
            if (chip != null) try { b.getClass().getMethod("setShortCriticalText", String.class).invoke(b, chip); } catch (Exception ignored) { }
            ((NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE)).notify(ID, b.build());
        } catch (Exception ignored) { }
    }

    static void clear(Context c) {
        try { ((NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE)).cancel(ID); } catch (Exception ignored) { }
    }
}
