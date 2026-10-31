package dev.kiyan.orion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.IBinder;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;

/** ORION's floating bubble: drag it anywhere, tap it to talk to ORION, long-press to hide it. */
public class BubbleService extends Service {
    private WindowManager wm;
    private ImageView bubble;

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        startAsForeground();
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        int size = (int) (58 * getResources().getDisplayMetrics().density);

        bubble = new ImageView(this);
        bubble.setImageResource(R.mipmap.ic_launcher);
        GradientDrawable ring = new GradientDrawable();
        ring.setShape(GradientDrawable.OVAL);
        ring.setColor(0xFF03101B);
        ring.setStroke((int) (2 * getResources().getDisplayMetrics().density), 0xFF3FD8FF);
        bubble.setBackground(ring);
        int pad = (int) (6 * getResources().getDisplayMetrics().density);
        bubble.setPadding(pad, pad, pad, pad);
        bubble.setElevation(12f);

        int type = Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;
        final WindowManager.LayoutParams p = new WindowManager.LayoutParams(size, size, type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT);
        p.gravity = Gravity.TOP | Gravity.START;
        p.x = 0;
        p.y = (int) (220 * getResources().getDisplayMetrics().density);

        bubble.setOnTouchListener(new View.OnTouchListener() {
            int sx, sy; float tx, ty; long down; boolean moved;
            @Override
            public boolean onTouch(View v, MotionEvent e) {
                switch (e.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        sx = p.x; sy = p.y; tx = e.getRawX(); ty = e.getRawY(); down = System.currentTimeMillis(); moved = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        int dx = (int) (e.getRawX() - tx), dy = (int) (e.getRawY() - ty);
                        if (Math.abs(dx) > 12 || Math.abs(dy) > 12) moved = true;
                        p.x = sx + dx; p.y = sy + dy;
                        wm.updateViewLayout(bubble, p);
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (!moved) {
                            if (System.currentTimeMillis() - down > 700) { stopSelf(); }
                            else { openApp("call"); }
                        }
                        return true;
                }
                return false;
            }
        });
        wm.addView(bubble, p);
    }

    private void openApp(String action) {
        Intent i = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (i == null) return;
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        i.putExtra("orion_action", action);
        startActivity(i);
    }

    private void startAsForeground() {
        String ch = "orion_bubble";
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel(ch, "ORION bubble", NotificationManager.IMPORTANCE_MIN));
        }
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, ch) : new Notification.Builder(this);
        Notification n = b.setContentTitle("ORION is standing by")
                .setContentText("Tap the bubble to talk · long-press it to hide")
                .setSmallIcon(android.R.drawable.ic_btn_speak_now).setOngoing(true).build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(7, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(7, n);
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (bubble != null && wm != null) {
            try { wm.removeView(bubble); } catch (Exception ignored) { }
        }
    }
}
