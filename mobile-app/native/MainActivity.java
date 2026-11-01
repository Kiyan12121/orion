package dev.kiyan.orion;

import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.view.WindowManager;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(OrionNativePlugin.class);
        super.onCreate(savedInstanceState);
        try {   // let ORION's voice play without a tap first (needed when a call opens the app)
            getBridge().getWebView().getSettings().setMediaPlaybackRequiresUserGesture(false);
        } catch (Exception ignored) { }
        wakeForCall(getIntent());
    }

    /** ORION calls / find-my-phone show over the lock screen and turn the screen on. */
    private void wakeForCall(Intent i) {
        if (i == null || i.getStringExtra("orion_action") == null) return;
        if (Build.VERSION.SDK_INT >= 27) { setShowWhenLocked(true); setTurnScreenOn(true); }
        else getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);   // so the bubble's "call" action reaches the app when it's already open
        wakeForCall(intent);
    }
}
