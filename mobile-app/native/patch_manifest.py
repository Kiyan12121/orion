"""Adds ORION's permissions, app-visibility query and bubble service to the generated AndroidManifest."""
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
perms = ["android.permission.RECORD_AUDIO", "android.permission.MODIFY_AUDIO_SETTINGS",
         "android.permission.POST_NOTIFICATIONS", "android.permission.SYSTEM_ALERT_WINDOW",
         "com.android.alarm.permission.SET_ALARM", "android.permission.VIBRATE",
         "android.permission.FOREGROUND_SERVICE", "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
         "android.permission.WAKE_LOCK", "android.permission.SCHEDULE_EXACT_ALARM",
         "android.permission.USE_FULL_SCREEN_INTENT", "android.permission.RECEIVE_BOOT_COMPLETED",
         "android.permission.INTERNET", "android.permission.ACCESS_NOTIFICATION_POLICY",
         "android.permission.ACCESS_FINE_LOCATION", "android.permission.ACCESS_COARSE_LOCATION",
         "android.permission.ACCESS_BACKGROUND_LOCATION", "android.permission.FOREGROUND_SERVICE_LOCATION",
         "android.permission.FOREGROUND_SERVICE_MICROPHONE", "android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS"]
block = "".join(f'    <uses-permission android:name="{x}" />\n' for x in perms if x not in s)
block += ('    <queries>\n        <intent>\n            <action android:name="android.intent.action.MAIN" />\n'
          '            <category android:name="android.intent.category.LAUNCHER" />\n        </intent>\n    </queries>\n')
s = s.replace("<application", block + "\n    <application", 1)
if "usesCleartextTraffic" not in s:
    s = s.replace("<application", '<application android:usesCleartextTraffic="true"', 1)
service = ('        <service android:name=".BubbleService" android:exported="false" '
           'android:foregroundServiceType="specialUse">\n'
           '            <property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" '
           'android:value="Floating assistant bubble" />\n        </service>\n'
           '        <service android:name=".LinkService" android:exported="false" '
           'android:foregroundServiceType="specialUse|location">\n'
           '            <property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" '
           'android:value="Keeps the phone linked to the user\'s own PC assistant for incoming calls" />\n        </service>\n'
           '        <service android:name=".HotwordService" android:exported="false" android:foregroundServiceType="microphone" />\n'
           '        <service android:name=".OrionAssistService" android:exported="true" android:permission="android.permission.BIND_VOICE_INTERACTION">\n'
           '            <meta-data android:name="android.voice_interaction" android:resource="@xml/orion_assist" />\n'
           '            <intent-filter><action android:name="android.service.voice.VoiceInteractionService" /></intent-filter>\n'
           '        </service>\n'
           '        <service android:name=".OrionSessionService" android:exported="true" android:permission="android.permission.BIND_VOICE_INTERACTION" />\n'
           '        <service android:name=".OrionRecognitionService" android:exported="true">\n'
           '            <intent-filter><action android:name="android.speech.RecognitionService" /><category android:name="android.intent.category.DEFAULT" /></intent-filter>\n'
           '            <meta-data android:name="android.speech" android:resource="@xml/orion_recognizer" />\n'
           '        </service>\n'
           '        <receiver android:name=".BootReceiver" android:exported="true">\n'
           '            <intent-filter><action android:name="android.intent.action.BOOT_COMPLETED" /></intent-filter>\n'
           '        </receiver>\n')
s = s.replace("</application>", service + "    </application>", 1)
s = re.sub(r'(<activity[^>]*?)android:launchMode="[^"]*"', r'\1', s)
s = s.replace('<activity', '<activity android:launchMode="singleTask"', 1)
# earbud / side-key assistant shortcut also opens ORION
s = s.replace('</activity>', '    <intent-filter><action android:name="android.intent.action.ASSIST" />'
              '<category android:name="android.intent.category.DEFAULT" /></intent-filter>\n        </activity>', 1)
open(p, "w", encoding="utf-8").write(s)
print("manifest patched")
