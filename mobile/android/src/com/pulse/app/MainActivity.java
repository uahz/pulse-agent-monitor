package com.pulse.app;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Vibrator;
import android.view.View;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * PULSE · 项目脉搏
 * 原生 WebView 容器：全离线加载 assets 中的 Web App，
 * 并通过 JavascriptInterface 暴露振动、版本、Toast 等原生能力。
 */
public class MainActivity extends Activity {

    private static final int COLOR_BG = Color.parseColor("#0F172A");
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        Window window = getWindow();
        window.setStatusBarColor(COLOR_BG);
        window.setNavigationBarColor(COLOR_BG);

        webView = new WebView(this);
        webView.setBackgroundColor(COLOR_BG);
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setScrollBarStyle(View.SCROLLBARS_INSIDE_OVERLAY);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setUseWideViewPort(false);
        settings.setLoadWithOverviewMode(false);
        settings.setTextZoom(100);
        // v1.4.0：扫码面板需要 <video> 自动播放相机预览
        settings.setMediaPlaybackRequiresUserGesture(false);

        // v1.4.0：扫码需要 CAMERA 运行时权限（minSdk 24，API 23+ 动态申请）
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, 1001);
        }

        webView.addJavascriptInterface(new NativeBridge(), "Android");

        // v1.4.0：把 WebRTC 的相机授权请求放行给已获系统权限的 App
        // 仅放行 VIDEO_CAPTURE，其它资源一律拒绝，避免扩大权限面
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(new Runnable() {
                    @Override public void run() {
                        java.util.ArrayList<String> allow = new java.util.ArrayList<String>();
                        for (String r : request.getResources()) {
                            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(r)) allow.add(r);
                        }
                        if (!allow.isEmpty()) request.grant(allow.toArray(new String[0]));
                        else request.deny();
                    }
                });
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                return !url.startsWith("file:///android_asset/");
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return !url.startsWith("file:///android_asset/");
            }
        });

        webView.clearCache(true);
        webView.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public void onBackPressed() {
        if (webView == null) {
            super.onBackPressed();
            return;
        }
        webView.evaluateJavascript(
                "(function(){ return !!(window.App && window.App.onBack()); })()",
                new ValueCallback<String>() {
                    @Override
                    public void onReceiveValue(String value) {
                        if (!"true".equals(value)) {
                            finish();
                        }
                    }
                });
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    private final class NativeBridge {

        @JavascriptInterface
        public void vibrate(int milliseconds) {
            try {
                Vibrator vibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
                if (vibrator != null && vibrator.hasVibrator()) {
                    vibrator.vibrate(milliseconds);
                }
            } catch (Exception ignored) {
                // 部分设备无振动器，静默降级
            }
        }

        @JavascriptInterface
        public String getVersion() {
            return "1.5.0";
        }

        /**
         * 局域网 HTTP GET 桥：由 Web 层 window.PulseLink.get(url) 调用。
         * 在子线程执行网络请求，结果通过 evaluateJavascript 回到主线程 Web 层，
         * 从而绕开 file:// 页面的跨域与明文流量限制。
         * 成功回调 window.PulseLink._onData(jsonText)，失败回调 _onError(message)。
         * v1.5.0：readTimeout 提升到 15s 以支持 /api/poll 长轮询挂起（默认 8s）。
         */
        @JavascriptInterface
        public void httpGet(final String url) {
            httpGetT(url, 15000);
        }

        /**
         * 带读超时的版本：长轮询（PulseLink poll 模式）传 15000，
         * 普通 GET 传更短超时。参数来自 JS 层，需防御非法值。
         */
        @JavascriptInterface
        public void httpGetT(final String url, final int timeoutMs) {
            final int timeout = (timeoutMs >= 1000 && timeoutMs <= 60000) ? timeoutMs : 15000;
            new Thread(new Runnable() {
                @Override
                public void run() {
                    HttpURLConnection conn = null;
                    try {
                        URL u = new URL(url);
                        conn = (HttpURLConnection) u.openConnection();
                        conn.setRequestMethod("GET");
                        conn.setConnectTimeout(Math.min(6000, timeout));
                        conn.setReadTimeout(timeout);
                        conn.setRequestProperty("Accept", "application/json");
                        int code = conn.getResponseCode();
                        InputStream in = (code >= 200 && code < 300)
                                ? conn.getInputStream() : conn.getErrorStream();
                        String body = readAll(in);
                        if (in != null) { try { in.close(); } catch (Exception ignored) {} }
                        final String script = (code >= 200 && code < 300)
                                ? "window.PulseLink&&window.PulseLink._onData(" + jsQuote(body) + ")"
                                : "window.PulseLink&&window.PulseLink._onError(" + jsQuote("HTTP " + code) + ")";
                        runOnUiThread(new Runnable() {
                            @Override public void run() { webView.evaluateJavascript(script, null); }
                        });
                    } catch (final Exception e) {
                        final String script = "window.PulseLink&&window.PulseLink._onError("
                                + jsQuote(String.valueOf(e.getMessage())) + ")";
                        runOnUiThread(new Runnable() {
                            @Override public void run() { webView.evaluateJavascript(script, null); }
                        });
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                }
            }, "pulse-http").start();
        }

        private String readAll(InputStream in) throws Exception {
            if (in == null) return "";
            java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) != -1) bos.write(buf, 0, n);
            return new String(bos.toByteArray(), "UTF-8");
        }

        /** 把任意文本转义为安全的 JS 字符串字面量。 */
        private String jsQuote(String s) {
            if (s == null) return "\"\"";
            StringBuilder b = new StringBuilder("\"");
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                switch (c) {
                    case '\\': b.append("\\\\"); break;
                    case '"':  b.append("\\\""); break;
                    case '\n': b.append("\\n"); break;
                    case '\r': b.append("\\r"); break;
                    case '\t': b.append("\\t"); break;
                    default:
                        if (c < 0x20 || c == '\u2028' || c == '\u2029')
                            b.append(String.format("\\u%04x", (int) c));
                        else b.append(c);
                }
            }
            return b.append("\"").toString();
        }

        @JavascriptInterface
        public void toast(final String message) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show();
                }
            });
        }
    }
}
