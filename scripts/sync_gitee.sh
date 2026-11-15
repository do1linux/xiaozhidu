#!/usr/bin/env bash
# 服务器唯一入口：常驻轮询 Gitee、有更新才重建、重建后健康检查。
#
#   ./sync_gitee.sh              常驻轮询（默认，间隔 SYNC_INTERVAL 秒）
#   ./sync_gitee.sh --once       只跑一轮，退出码即本轮结果（手动 / 调试用）
#   ./sync_gitee.sh --install    生成 systemd 自启单元并启用（幂等，同名覆盖）
#
# 可调环境变量：REPO_DIR / BRANCH / SYNC_INTERVAL / HEALTH_URL / LOG_FILE / DRY_RUN
# 日志只落结论与提交短哈希，不落远端地址、凭据、本机路径与用户数据。
set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
LOG_FILE="${LOG_FILE:-$REPO_DIR/logs/sync.log}"
LOCK_FILE="${LOCK_FILE:-${TMPDIR:-/tmp}/voice-bridge-sync.lock}"
SYNC_INTERVAL="${SYNC_INTERVAL:-300}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8100/healthz}"
UNIT_NAME="voice-bridge-sync"
UNIT_PATH="/etc/systemd/system/${UNIT_NAME}.service"

mkdir -p "$(dirname "$LOG_FILE")"
exec >>"$LOG_FILE" 2>&1

log() { echo "[$(date '+%F %T')] $*"; }

rotate_log() {
    if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt 5242880 ]; then
        : >"$LOG_FILE"
    fi
    return 0
}

install_unit() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "需要 root：sudo $SCRIPT_PATH --install" >&2
        return 1
    fi
    cat >"$UNIT_PATH" <<UNIT
[Unit]
Description=voice-bridge Gitee sync daemon
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=REPO_DIR=$REPO_DIR
ExecStart=$SCRIPT_PATH daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now "$UNIT_NAME"
    log "systemd 单元已启用：$UNIT_NAME"
    echo "已启用：$UNIT_NAME（查看状态：systemctl status $UNIT_NAME）"
}

sync_once() {
    rotate_log
    cd "$REPO_DIR" || { log "部署目录不可达，放弃本轮"; return 1; }

    local branch old_commit new_commit i
    branch="${BRANCH:-$(git -C "$REPO_DIR" symbolic-ref --short HEAD 2>/dev/null || echo main)}"
    old_commit=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo none)

    # stderr 一律丢弃：远端地址可能带凭据，不进日志
    if ! git -C "$REPO_DIR" fetch --prune origin "$branch" --quiet >/dev/null 2>&1; then
        log "git fetch 失败（网络或权限），本轮放弃"
        return 1
    fi
    if ! git -C "$REPO_DIR" reset --hard "origin/$branch" --quiet >/dev/null 2>&1; then
        log "reset 到远端分支失败，本轮放弃"
        return 1
    fi
    new_commit=$(git -C "$REPO_DIR" rev-parse HEAD)

    if docker compose version >/dev/null 2>&1; then
        DC=(docker compose)
    else
        DC=(docker-compose)
    fi

    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "DRY_RUN：跳过重建与健康检查（${old_commit:0:8} -> ${new_commit:0:8}，分支 $branch）"
        return 0
    fi

    if [ "$old_commit" != "$new_commit" ]; then
        log "检测到更新 ${old_commit:0:8} -> ${new_commit:0:8}，开始重建"
        if ! "${DC[@]}" build --quiet; then
            log "镜像构建失败，保留旧容器继续运行"
            return 1
        fi
        if ! "${DC[@]}" up -d --remove-orphans; then
            log "容器启动失败，本轮放弃"
            return 1
        fi
    elif [ -z "$("${DC[@]}" ps -q --status running 2>/dev/null)" ]; then
        log "服务未运行，拉起容器（代码无更新）"
        if ! "${DC[@]}" up -d --remove-orphans; then
            log "容器启动失败，本轮放弃"
            return 1
        fi
    else
        log "无更新（${new_commit:0:8}），跳过重建"
    fi

    for i in $(seq 1 10); do
        if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
            log "健康检查通过（${new_commit:0:8}）"
            return 0
        fi
        sleep 2
    done
    log "警告：健康检查未通过，人工介入：${DC[*]} logs --tail=100"
    return 2
}

run_round() {
    exec 9>"$LOCK_FILE"
    if ! flock -n 9; then
        log "上一轮仍在进行，跳过本轮"
        return 0
    fi
    sync_once || return $?
}

case "${1:-daemon}" in
    --install)
        install_unit
        ;;
    --once)
        run_round
        ;;
    daemon|"")
        trap 'log "收到停止信号，退出"; exit 0' TERM INT
        log "===== 守护启动（间隔 ${SYNC_INTERVAL}s）====="
        while true; do
            run_round || log "本轮失败，${SYNC_INTERVAL}s 后重试"
            sleep "$SYNC_INTERVAL" & wait $!
        done
        ;;
    *)
        echo "用法：$0 [daemon|--once|--install]" >&2
        exit 64
        ;;
esac
