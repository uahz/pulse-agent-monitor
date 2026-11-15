#!/usr/bin/env bash
# =========================================================
#  PULSE · 项目脉搏  ——  Android APK 构建脚本
#  纯命令行构建（aapt2 / javac / d8 / zipalign / apksigner）
#  不依赖 Gradle 与 Android Studio，产物为可直接安装的签名 APK
# =========================================================
set -euo pipefail

SDK="${ANDROID_HOME:-/opt/android-sdk}"
BT="$SDK/build-tools/35.0.0"
PLATFORM="$SDK/platforms/android-35/android.jar"
ROOT="$(cd "$(dirname "$0")" && pwd)"
# 仓库结构：mobile/android/build.sh，页面源码在 mobile/index.html 与 mobile/fonts/
WEB="$ROOT/.."
OUT="$ROOT/build"
# 预编译签名包放在仓库 releases/；可用 PULSE_APK_OUT 覆盖输出位置
APK="${PULSE_APK_OUT:-$ROOT/../../releases/PULSE_v1.4.0.apk}"
# 演示签名：keystore 与口令均为本地生成、不入库（.gitignore）。
# 口令优先取环境变量；否则沿用本地缓存；首次构建自动生成随机口令。
KS_PASS_FILE="$ROOT/.keystore.pass"
if [ -n "${PULSE_KS_PASS:-}" ]; then
  KS_PASS="$PULSE_KS_PASS"
elif [ -f "$KS_PASS_FILE" ]; then
  KS_PASS="$(cat "$KS_PASS_FILE")"
else
  KS_PASS="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 20)"
  printf '%s' "$KS_PASS" > "$KS_PASS_FILE"
  chmod 600 "$KS_PASS_FILE"
fi

for p in "$BT/aapt2" "$BT/d8" "$BT/zipalign" "$BT/apksigner" "$PLATFORM"; do
  [ -e "$p" ] || { echo "缺少构建工具: $p"; exit 1; }
done

echo "[0/8] 清理并准备目录"
rm -rf "$OUT" "$ROOT/assets"
mkdir -p "$OUT/compiled" "$OUT/gen" "$OUT/classes" "$OUT/dex" "$ROOT/assets"
cp "$WEB/index.html" "$ROOT/assets/"
cp -r "$WEB/fonts" "$ROOT/assets/"

echo "[1/8] 编译资源 (aapt2 compile)"
"$BT/aapt2" compile --dir "$ROOT/res" -o "$OUT/compiled/"
mapfile -t FLATS < <(find "$OUT/compiled" -name '*.flat' | sort)
printf '       %s 个资源条目\n' "${#FLATS[@]}"

echo "[2/8] 链接资源并生成 R.java (aapt2 link)"
"$BT/aapt2" link -o "$OUT/base.apk" \
  -I "$PLATFORM" \
  --manifest "$ROOT/AndroidManifest.xml" \
  --java "$OUT/gen" \
  -A "$ROOT/assets" \
  -0 woff2 \
  --min-sdk-version 24 --target-sdk-version 35 \
  --version-code 10 --version-name 1.4.0 \
  "${FLATS[@]}"

echo "[3/8] 编译 Java 源码 (javac)"
mapfile -t SRCS < <(find "$OUT/gen" "$ROOT/src" -name '*.java' | sort)
javac -source 8 -target 8 -encoding UTF-8 -nowarn -Xlint:none \
  -classpath "$PLATFORM" -d "$OUT/classes" "${SRCS[@]}"

echo "[4/8] 转换为 DEX (d8)"
mapfile -t CLASSES < <(find "$OUT/classes" -name '*.class' | sort)
"$BT/d8" --lib "$PLATFORM" --min-api 24 --output "$OUT/dex" "${CLASSES[@]}"

echo "[5/8] 将 classes.dex 写入 APK"
(cd "$OUT/dex" && "$BT/aapt" add "$OUT/base.apk" classes.dex > /dev/null)

echo "[6/8] 对齐 (zipalign)"
"$BT/zipalign" -f 4 "$OUT/base.apk" "$OUT/aligned.apk"

echo "[7/8] 生成签名密钥（仅首次）"
if [ ! -f "$ROOT/pulse.keystore" ]; then
  keytool -genkeypair \
    -keystore "$ROOT/pulse.keystore" \
    -storetype PKCS12 \
    -alias pulse -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass "$KS_PASS" -keypass "$KS_PASS" \
    -dname "CN=PULSE, OU=Mobile, O=PulseApp, L=Shenzhen, ST=Guangdong, C=CN" 2>/dev/null
fi

echo "[8/8] 签名 (v1 + v2)"
"$BT/apksigner" sign \
  --ks "$ROOT/pulse.keystore" --ks-key-alias pulse \
  --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
  --v1-signing-enabled true --v2-signing-enabled true \
  --out "$APK" "$OUT/aligned.apk"

echo "-----------------------------------"
"$BT/apksigner" verify --verbose "$APK" | head -8
"$BT/aapt" dump badging "$APK" | head -4
ls -lh "$APK"
echo "BUILD_OK: $APK"
