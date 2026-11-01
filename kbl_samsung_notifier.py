#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
🏀 서울 삼성 썬더스 (Seoul Samsung Thunders) KBL 실시간 스마트폰 푸시 알림봇 v3.0
   (컴퓨터를 완전히 꺼두어도 작동하는 무료 클라우드 GitHub Actions 완벽 호환 버전)
================================================================================
- 데이터 출처: 네이버 스포츠 API (api-gw.sports.naver.com) & KBL 공식 API (api.kbl.or.kr)
- 대상 경기: 서울 삼성 썬더스 (팀 코드: 35) 전 경기 자동 필터링
- 시간대 기준: 대한민국 표준시 (KST, UTC+9) 고정 — 해외 클라우드 서버에서도 정확한 시간 작동
- 핵심 맞춤형 알림 기능:
  1) [경기 시작 30분 전] 양 팀 선발 라인업(베스트 5) 알림
  2) [1~3쿼터 종료 시점] 각 쿼터 내용 요약 알림
     - 서울 삼성 선수: 득점 + 리바운드/어시스트 등 구체적 기록 표기
       (예: 칸터 12점 3리바운드, 맥컬러 8점 3리바운드, 이관희 6점 3어시스트)
     - 상대 팀 선수: 주요 득점자 득점만 간단 표기 (예: 베스 8점, 문정현 5점)
  3) [4쿼터 종료 시점]
     - 동점(연장 돌입) 시: 4쿼터 종료(연장 돌입) 및 4쿼터 선수 요약 알림 먼저 발송
     - 정규 종료 시: 최종 결과 + 경기 MVP + 서울 삼성 주요 선수 기록 통합 발송
  4) [최종 경기 종료 (4쿼터 종료 또는 연장 종료 후)]
     - 공헌도 기반 경기 MVP 선정 및 주관적 한줄평
     - 서울 삼성 주요 선수들의 핵심 기록 맞춤형 요약
       (예: 경기 MVP 칸터 32점 13리바운드, 이규태 15점 3점슛 3/6,
            한호빈 12점 6어시스트, 구탕 11점 5리바운드 4어시스트)
  5) [컴퓨터 전원 OFF 지원]
     - 클라우드 스마트 실행 모드: python kbl_samsung_notifier.py --cloud-auto
       (오늘 삼성 경기가 없으면 1초 만에 자동 종료, 경기가 있으면 경기 30분 전부터
        경기 끝날 때까지 25초 주기로 실시간 감시 후 자동 종료!)
================================================================================
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# 대한민국 표준시 (KST = UTC+9) — 해외 클라우드(GitHub Actions 등)에서도 한국 시간 기준 작동
KST = datetime.timezone(datetime.timedelta(hours=9))


def now_kst() -> datetime.datetime:
    return datetime.datetime.now(tz=KST)


# ==============================================================================
# 1. 사용자 환경 설정 (초기 세팅 시 NTFY_TOPIC만 확인하세요!)
# ==============================================================================

# 스마트폰 'ntfy' 앱에서 구독(Subscribe)한 토픽 이름과 똑같이 적어주세요.
NTFY_TOPIC: str = os.environ.get("NTFY_TOPIC", "samsung-thunders-kbl-alert")
NTFY_SERVER: str = "https://ntfy.sh"

# 선택 사항: 텔레그램 / 디스코드 동시 발송용
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL: str = os.environ.get("DISCORD_WEBHOOK_URL", "")

# 응원 팀 고정 (서울 삼성 썬더스)
TARGET_TEAM_NAME: str = "서울 삼성"
TARGET_TEAM_SHORT: str = "삼성"
TARGET_KBL_TEAM_CODE: str = "35"

# 경기 시작 몇 분 전부터 선발 라인업 알림을 보낼지 설정 (기본: 30분 전)
LINEUP_ALERT_MINUTES_BEFORE: int = 30

# 실시간 조회 주기 (초 단위)
POLL_INTERVAL_SECONDS: int = 25

# 발송 상태 및 쿼터별 누적 기록 저장 파일
STATE_FILE_PATH: Path = Path(__file__).resolve().parent / "kbl_samsung_state.json"


# ==============================================================================
# 2. 데이터 모델 정의
# ==============================================================================

@dataclass
class PlayerStat:
    """개별 선수의 박스스코어 기록 모델"""
    player_id: str
    name: str
    team: str
    position: str = ""
    is_starter: bool = False
    points: int = 0
    rebounds: int = 0
    off_rebounds: int = 0
    assists: int = 0
    steals: int = 0
    blocks: int = 0
    turnovers: int = 0
    three_pm: int = 0   # 3점슛 성공 개수
    three_pa: int = 0   # 3점슛 시도 개수
    fg_missed: int = 0
    ft_missed: int = 0
    fouls: int = 0

    def calculate_kbl_contribution(self, is_winning_team: bool = False) -> float:
        """KBL 공헌도 산출 공식"""
        score = (
            self.points * 1.0
            + self.rebounds * 1.2
            + self.off_rebounds * 0.4
            + self.assists * 1.5
            + self.steals * 2.0
            + self.blocks * 2.0
            + self.three_pm * 0.5
            - self.turnovers * 1.5
            - self.fg_missed * 0.4
            - self.ft_missed * 0.3
            - self.fouls * 0.2
        )
        if is_winning_team:
            score += 3.5
        return round(score, 1)

    def format_samsung_quarter_line(self) -> str:
        """
        [요구사항 2] 1~3쿼터 종료 시 서울 삼성 선수용 구체적 기록 포맷
        예: '칸터 12점 3리바운드', '맥컬러 8점 3리바운드', '이관희 6점 3어시스트'
        """
        parts = [f"{self.name} {self.points}점"]
        if self.rebounds >= 2:
            parts.append(f"{self.rebounds}리바운드")
        if self.assists >= 2:
            parts.append(f"{self.assists}어시스트")
        if self.three_pm >= 2 and self.rebounds < 2 and self.assists < 2:
            parts.append(f"3점슛 {self.three_pm}개")
        if self.steals >= 2:
            parts.append(f"{self.steals}스틸")
        if self.blocks >= 2:
            parts.append(f"{self.blocks}블록")
        return " ".join(parts)

    def format_opponent_quarter_line(self) -> str:
        """
        [요구사항 2] 1~3쿼터 종료 시 상대 팀 선수용 간단 득점 포맷
        예: '베스 8점', '문정현 5점'
        """
        return f"{self.name} {self.points}점"

    def format_samsung_final_key_line(self, is_mvp: bool = False) -> str:
        """
        [요구사항 3] 경기 종료 후 서울 삼성 주요 선수 핵심 기록 포맷
        예:
        - 경기 MVP 칸터 32점 13리바운드
        - 이규태 15점 3점슛 3/6
        - 한호빈 12점 6어시스트
        - 구탕 11점 5리바운드 4어시스트
        """
        prefix = f"👑 경기 MVP {self.name}" if is_mvp else f"• {self.name}"
        details = [f"{self.points}점"]

        if self.rebounds >= 4:
            details.append(f"{self.rebounds}리바운드")
        if self.assists >= 3:
            details.append(f"{self.assists}어시스트")
        if self.three_pm >= 2:
            if self.three_pa >= self.three_pm:
                details.append(f"3점슛 {self.three_pm}/{self.three_pa}")
            else:
                details.append(f"3점슛 {self.three_pm}개")
        if self.steals >= 2:
            details.append(f"{self.steals}스틸")
        if self.blocks >= 2:
            details.append(f"{self.blocks}블록")

        return f"{prefix}: {' '.join(details)}"


@dataclass
class GameSnapshot:
    """실시간 경기 스냅샷"""
    game_id: str
    game_date: str
    start_time: str  # "HH:MM" (KST)
    venue: str
    home_team: str
    away_team: str
    status_code: str
    current_period: int = 0
    is_period_finished: bool = False
    is_game_finished: bool = False
    home_score: int = 0
    away_score: int = 0
    home_period_scores: List[int] = field(default_factory=list)
    away_period_scores: List[int] = field(default_factory=list)
    home_starters: List[str] = field(default_factory=list)
    away_starters: List[str] = field(default_factory=list)
    players: List[PlayerStat] = field(default_factory=list)
    quarter_only_players: List[PlayerStat] = field(default_factory=list)


# ==============================================================================
# 3. 쿼터별 단일 기록 추출 및 수훈 선수(MVP) 분석 엔진
# ==============================================================================

def is_samsung_team(team_name: str) -> bool:
    return TARGET_TEAM_SHORT in team_name or TARGET_TEAM_NAME in team_name


def compute_quarter_delta_stats(
    current_players: List[PlayerStat],
    prev_cumulative_map: Dict[str, Dict[str, int]],
) -> List[PlayerStat]:
    delta_list: List[PlayerStat] = []
    for p in current_players:
        prev = prev_cumulative_map.get(p.player_id or p.name, {})
        q_pts = max(0, p.points - int(prev.get("points", 0)))
        q_reb = max(0, p.rebounds - int(prev.get("rebounds", 0)))
        q_oreb = max(0, p.off_rebounds - int(prev.get("off_rebounds", 0)))
        q_ast = max(0, p.assists - int(prev.get("assists", 0)))
        q_stl = max(0, p.steals - int(prev.get("steals", 0)))
        q_blk = max(0, p.blocks - int(prev.get("blocks", 0)))
        q_tpm = max(0, p.three_pm - int(prev.get("three_pm", 0)))
        q_tpa = max(0, p.three_pa - int(prev.get("three_pa", 0)))

        if q_pts > 0 or q_reb >= 2 or q_ast >= 2:
            delta_list.append(
                PlayerStat(
                    player_id=p.player_id or p.name,
                    name=p.name,
                    team=p.team,
                    position=p.position,
                    points=q_pts,
                    rebounds=q_reb,
                    off_rebounds=q_oreb,
                    assists=q_ast,
                    steals=q_stl,
                    blocks=q_blk,
                    three_pm=q_tpm,
                    three_pa=q_tpa,
                )
            )
    return delta_list


def evaluate_mvp_and_samsung_leaders(
    snapshot: GameSnapshot,
) -> Tuple[Optional[PlayerStat], float, str, List[str]]:
    if not snapshot.players:
        return None, 0.0, "선수별 상세 기록 집계 대기 중입니다.", []

    winning_team = ""
    if snapshot.home_score > snapshot.away_score:
        winning_team = snapshot.home_team
    elif snapshot.away_score > snapshot.home_score:
        winning_team = snapshot.away_team

    ranked_all: List[Tuple[float, PlayerStat]] = []
    for p in snapshot.players:
        is_win = bool(winning_team and (p.team in winning_team or winning_team in p.team))
        c_score = p.calculate_kbl_contribution(is_winning_team=is_win)
        ranked_all.append((c_score, p))

    ranked_all.sort(key=lambda x: (x[0], x[1].points, x[1].rebounds, x[1].assists), reverse=True)

    samsung_ranked: List[Tuple[float, PlayerStat]] = [
        (c, p) for c, p in ranked_all if is_samsung_team(p.team)
    ]
    samsung_ranked.sort(key=lambda x: (x[1].points, x[0], x[1].rebounds, x[1].assists), reverse=True)

    if samsung_ranked and is_samsung_team(winning_team):
        mvp_contrib, mvp = max(samsung_ranked, key=lambda x: x[0])
    else:
        mvp_contrib, mvp = ranked_all[0]

    comments: List[str] = []
    if mvp.points >= 10 and mvp.rebounds >= 10:
        comments.append(f"{mvp.points}점 {mvp.rebounds}리바운드 더블더블로 골밑과 공격을 완벽히 장악했습니다")
    elif mvp.points >= 10 and mvp.assists >= 10:
        comments.append(f"{mvp.points}점 {mvp.assists}어시스트 더블더블로 코트 위 야전사령관 역할을 해냈습니다")
    elif mvp.points >= 25:
        comments.append(f"폭발적인 {mvp.points}점 득점포로 승부처마다 상대 수비를 무너뜨렸습니다")
    elif mvp.three_pm >= 3:
        comments.append(f"고비마다 터진 외곽 3점포({mvp.three_pm}개)로 경기 흐름을 주도했습니다")
    else:
        comments.append("공수 양면에서 가장 높은 공헌도를 기록하며 팀의 중심을 잡았습니다")

    if mvp.steals + mvp.blocks >= 3:
        comments.append(f"수비에서도 스틸 {mvp.steals}개·블록 {mvp.blocks}개로 결정적인 기여를 했습니다")

    subjective_comment = " / ".join(comments) + "."

    samsung_lines: List[str] = []
    if is_samsung_team(mvp.team):
        samsung_lines.append(mvp.format_samsung_final_key_line(is_mvp=True))

    for _, sp in samsung_ranked:
        if is_samsung_team(mvp.team) and sp.name == mvp.name:
            continue
        if sp.points >= 5 or sp.rebounds >= 5 or sp.assists >= 4:
            samsung_lines.append(sp.format_samsung_final_key_line(is_mvp=False))
        if len(samsung_lines) >= 5:
            break

    return mvp, mvp_contrib, subjective_comment, samsung_lines


# ==============================================================================
# 4. 알림 메시지 포맷터
# ==============================================================================

def format_lineup_message(snap: GameSnapshot) -> Tuple[str, str]:
    title = f"[경기 시작 30분 전 · 선발 라인업] {snap.away_team} vs {snap.home_team}"
    home_lineup = ", ".join(snap.home_starters) if snap.home_starters else "현장 발표 대기 중"
    away_lineup = ", ".join(snap.away_starters) if snap.away_starters else "현장 발표 대기 중"

    lines = [
        f"⏰ 경기 시작 30분 전! ({snap.game_date} {snap.start_time} 점프볼)",
        f"🏟️ 경기장: {snap.venue}",
        "",
        f"⚡ [{snap.home_team if is_samsung_team(snap.home_team) else snap.away_team} 선발 라인업]",
        f"   • {home_lineup if is_samsung_team(snap.home_team) else away_lineup}",
        "",
        f"🏀 [{snap.away_team if is_samsung_team(snap.home_team) else snap.home_team} 선발 라인업]",
        f"   • {away_lineup if is_samsung_team(snap.home_team) else home_lineup}",
    ]
    return title, "\n".join(lines)


def format_quarter_end_message(snap: GameSnapshot, quarter: int) -> Tuple[str, str]:
    is_tied_q4 = (quarter == 4 and snap.home_score == snap.away_score)
    if is_tied_q4:
        title = f"[4쿼터 종료 · 연장 돌입!] {snap.away_team} {snap.away_score} : {snap.home_score} {snap.home_team}"
    else:
        title = f"[{quarter}쿼터 종료] {snap.away_team} {snap.away_score} : {snap.home_score} {snap.home_team}"

    q_idx = quarter - 1
    if len(snap.home_period_scores) > q_idx and len(snap.away_period_scores) > q_idx:
        q_home_pts = snap.home_period_scores[q_idx]
        q_away_pts = snap.away_period_scores[q_idx]
        q_score_str = f"({quarter}쿼터 득점: {snap.away_team} {q_away_pts} : {q_home_pts} {snap.home_team})"
    else:
        q_score_str = ""

    source_players = snap.quarter_only_players if snap.quarter_only_players else snap.players
    samsung_q_players = [
        p for p in source_players if is_samsung_team(p.team) and (p.points > 0 or p.rebounds >= 2 or p.assists >= 2)
    ]
    opp_q_players = [
        p for p in source_players if not is_samsung_team(p.team) and p.points > 0
    ]

    samsung_q_players.sort(key=lambda p: (p.points, p.rebounds, p.assists), reverse=True)
    opp_q_players.sort(key=lambda p: p.points, reverse=True)

    opp_team_name = snap.away_team if is_samsung_team(snap.home_team) else snap.home_team

    samsung_summary = (
        ", ".join(p.format_samsung_quarter_line() for p in samsung_q_players[:3])
        if samsung_q_players
        else "주요 기록 집계 중"
    )
    opp_summary = (
        ", ".join(p.format_opponent_quarter_line() for p in opp_q_players[:2])
        if opp_q_players
        else "주요 기록 집계 중"
    )

    diff = abs(snap.home_score - snap.away_score)
    if snap.home_score > snap.away_score:
        lead_text = f"{snap.home_team} {diff}점 차 리드"
    elif snap.away_score > snap.home_score:
        lead_text = f"{snap.away_team} {diff}점 차 리드"
    else:
        lead_text = "동점 접전"

    lines = [
        f"📊 {quarter}쿼터 종료 스코어 ({lead_text})",
        f"   👉 {snap.away_team} {snap.away_score} : {snap.home_score} {snap.home_team} {q_score_str}".rstrip(),
        "",
        f"📝 [{quarter}쿼터 주요 활약 요약]",
        f"   ⚡ 서울 삼성: {samsung_summary}",
        f"   🏀 {opp_team_name}: {opp_summary}",
    ]

    if is_tied_q4:
        lines.extend([
            "",
            "🔥 4쿼터가 동점으로 종료되어 연장전(OT)에 돌입합니다!",
            "   연장 종료 후 최종 결과와 삼성 주요 선수 기록을 별도로 알려드립니다.",
        ])

    return title, "\n".join(lines)


def format_final_result_message(snap: GameSnapshot, went_to_overtime: bool) -> Tuple[str, str]:
    ot_badge = " (연장 종료)" if went_to_overtime else ""
    if went_to_overtime:
        title = f"[연장 최종 결과] {snap.away_team} {snap.away_score} : {snap.home_score} {snap.home_team}"
    else:
        title = f"[경기 최종 종료] {snap.away_team} {snap.away_score} : {snap.home_score} {snap.home_team}"

    samsung_is_home = is_samsung_team(snap.home_team)
    samsung_score = snap.home_score if samsung_is_home else snap.away_score
    opp_score = snap.away_score if samsung_is_home else snap.home_score
    win_banner = "🎉 서울 삼성 썬더스 승리!" if samsung_score > opp_score else "수고하셨습니다! (다음 경기 화이팅)"

    q_parts: List[str] = []
    for idx in range(min(len(snap.home_period_scores), len(snap.away_period_scores))):
        lbl = f"{idx + 1}Q" if idx < 4 else f"OT{idx - 3}"
        q_parts.append(f"{lbl} {snap.away_period_scores[idx]}:{snap.home_period_scores[idx]}")

    mvp, mvp_contrib, commentary, samsung_key_lines = evaluate_mvp_and_samsung_leaders(snap)

    lines = [
        f"🏁 경기 종료{ot_badge} — {win_banner}",
        f"   👉 최종 스코어: {snap.away_team} {snap.away_score} : {snap.home_score} {snap.home_team}",
    ]
    if q_parts:
        lines.append(f"   ({' / '.join(q_parts)})")

    lines.append("")
    if mvp:
        lines.extend([
            f"🏆 [오늘의 수훈 선수(MVP) 선정]",
            f"   • {mvp.name} ({mvp.team}) — 공헌도 {mvp_contrib}점",
            f"   • 한줄평: \"{commentary}\"",
            "",
        ])

    lines.append("⚡ [서울 삼성 주요 선수 기록]")
    if samsung_key_lines:
        for s_line in samsung_key_lines:
            lines.append(f"   {s_line}")
    else:
        lines.append("   • 상세 선수 기록 집계 중")

    return title, "\n".join(lines)


# ==============================================================================
# 5. 스마트폰 푸시 알림 발송 모듈 (ntfy / Telegram / Discord)
# ==============================================================================

class PushNotifier:
    def __init__(
        self,
        ntfy_topic: str = NTFY_TOPIC,
        telegram_token: str = TELEGRAM_BOT_TOKEN,
        telegram_chat_id: str = TELEGRAM_CHAT_ID,
        discord_webhook: str = DISCORD_WEBHOOK_URL,
        dry_run: bool = False,
    ) -> None:
        self.ntfy_topic = ntfy_topic.strip()
        self.telegram_token = telegram_token.strip()
        self.telegram_chat_id = telegram_chat_id.strip()
        self.discord_webhook = discord_webhook.strip()
        self.dry_run = dry_run

    def send(self, title: str, message: str, tags: str = "basketball,zap", priority: str = "high") -> None:
        now_str = now_kst().strftime("%Y-%m-%d %H:%M:%S KST")
        border = "=" * 70
        print(f"\n{border}")
        print(f"📲 [{now_str}] 푸시 알림 발송: {title}")
        print("-" * 70)
        print(message)
        print(f"{border}\n")

        if self.dry_run:
            return

        if self.ntfy_topic:
            self._send_ntfy(title=title, message=message, tags=tags, priority=priority)
        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(title=title, message=message)
        if self.discord_webhook:
            self._send_discord(title=title, message=message)

    def _send_ntfy(self, title: str, message: str, tags: str, priority: str) -> None:
        url = f"{NTFY_SERVER.rstrip('/')}/{urllib.parse.quote(self.ntfy_topic)}"
        full_body = f"【{title}】\n\n{message}".encode("utf-8")
        headers = {
            "Tags": tags,
            "Priority": priority,
            "Content-Type": "text/plain; charset=utf-8",
        }
        req = urllib.request.Request(url, data=full_body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    print(f"✅ [ntfy 스마트폰 푸시 전송 완료] 토픽: {self.ntfy_topic}")
        except Exception as exc:
            print(f"⚠️ [ntfy 전송 실패]: {exc}")

    def _send_telegram(self, title: str, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.telegram_chat_id,
            "text": f"🏀 *{title}*\n\n{message}",
            "parse_mode": "Markdown",
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                print("✅ [텔레그램 푸시 전송 완료]")
        except Exception as exc:
            print(f"⚠️ [텔레그램 전송 실패]: {exc}")

    def _send_discord(self, title: str, message: str) -> None:
        payload = json.dumps({"content": f"**🏀 {title}**\n```\n{message}\n```"}).encode("utf-8")
        req = urllib.request.Request(
            self.discord_webhook,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "KBL-Samsung-Notifier/3.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                print("✅ [디스코드 푸시 전송 완료]")
        except Exception as exc:
            print(f"⚠️ [디스코드 전송 실패]: {exc}")


# ==============================================================================
# 6. 네이버 스포츠 API & KBL 공식 API 실시간 데이터 수집기
# ==============================================================================

class KBLDataFetcher:
    NAVER_BASE = "https://api-gw.sports.naver.com"
    KBL_BASE = "https://api.kbl.or.kr"

    def __init__(self) -> None:
        self.common_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
        self.kbl_headers = {
            **self.common_headers,
            "Channel": "WEB",
            "TeamCode": "XX",
            "Origin": "https://www.kbl.or.kr",
            "Referer": "https://www.kbl.or.kr/",
        }

    def _get_json(self, url: str, headers: Dict[str, str]) -> Optional[Any]:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        return None

    def fetch_today_samsung_game(self, target_date: Optional[str] = None) -> Optional[GameSnapshot]:
        if not target_date:
            target_date = now_kst().strftime("%Y-%m-%d")

        snap = self._fetch_from_naver(target_date)
        if snap:
            return snap
        return self._fetch_from_kbl(target_date)

    def _fetch_from_naver(self, date_str: str) -> Optional[GameSnapshot]:
        sched_url = (
            f"{self.NAVER_BASE}/schedule/games?"
            f"fields=basic,schedule,basketball&upperCategoryId=kbasketball&categoryId=kbl"
            f"&fromDate={date_str}&toDate={date_str}"
        )
        data = self._get_json(sched_url, self.common_headers)
        if not data or not isinstance(data, dict):
            return None

        games = data.get("result", {}).get("games", [])
        target_game = None
        for g in games:
            home_name = str(g.get("homeTeamName", ""))
            away_name = str(g.get("awayTeamName", ""))
            if is_samsung_team(home_name) or is_samsung_team(away_name):
                target_game = g
                break

        if not target_game:
            return None

        game_id = str(target_game.get("gameId", ""))
        status_code_raw = str(target_game.get("statusCode", "BEFORE")).upper()
        status_info = str(target_game.get("statusInfo", ""))

        snap = GameSnapshot(
            game_id=game_id,
            game_date=date_str,
            start_time=str(target_game.get("gameDateTime", ""))[11:16] or "19:00",
            venue=str(target_game.get("stadium", "잠실학생체육관")),
            home_team=str(target_game.get("homeTeamName", "홈팀")),
            away_team=str(target_game.get("awayTeamName", "원정팀")),
            status_code=status_code_raw,
            home_score=int(target_game.get("homeTeamScore", 0) or 0),
            away_score=int(target_game.get("awayTeamScore", 0) or 0),
        )

        if status_code_raw in ("RESULT", "END", "FINAL", "ENDED"):
            snap.is_game_finished = True
            snap.current_period = 4
        elif "연장" in status_info or "OT" in status_info.upper():
            snap.current_period = 5
            snap.is_period_finished = ("종료" in status_info)
        else:
            for q in (1, 2, 3, 4):
                if f"{q}쿼터" in status_info or f"{q}Q" in status_info.upper():
                    snap.current_period = q
                    snap.is_period_finished = ("종료" in status_info)
                    break

        lineup_data = self._get_json(f"{self.NAVER_BASE}/schedule/games/{game_id}/lineup", self.common_headers)
        if lineup_data and isinstance(lineup_data, dict):
            res = lineup_data.get("result", {})
            for side_key, target_list in (("homeLineup", snap.home_starters), ("awayLineup", snap.away_starters)):
                entries = res.get(side_key, [])
                if isinstance(entries, list):
                    for p in entries:
                        if p.get("isStarter", True):
                            p_name = p.get("playerName") or p.get("name")
                            p_pos = p.get("positionName") or p.get("pos", "")
                            if p_name:
                                target_list.append(f"{p_name}({p_pos})" if p_pos else str(p_name))

        rec_data = self._get_json(f"{self.NAVER_BASE}/schedule/games/{game_id}/record", self.common_headers)
        if rec_data and isinstance(rec_data, dict):
            res = rec_data.get("result", {}).get("recordData", {}) or rec_data.get("result", {})
            score_table = res.get("quarterScore") or res.get("periodScores") or {}
            if isinstance(score_table, dict):
                for q_key in ("q1", "q2", "q3", "q4", "ot1", "ot2"):
                    h_q = score_table.get("home", {}).get(q_key)
                    a_q = score_table.get("away", {}).get(q_key)
                    if h_q is not None and a_q is not None:
                        snap.home_period_scores.append(int(h_q))
                        snap.away_period_scores.append(int(a_q))

            for side_key, team_label in (
                ("homePlayerStats", snap.home_team),
                ("awayPlayerStats", snap.away_team),
                ("homePlayers", snap.home_team),
                ("awayPlayers", snap.away_team),
            ):
                p_list = res.get(side_key, [])
                if isinstance(p_list, list):
                    for item in p_list:
                        p_name = item.get("playerName") or item.get("name")
                        if not p_name:
                            continue
                        fg_a = int(item.get("fgAttempted", item.get("fga", 0)) or 0)
                        fg_m = int(item.get("fgMade", item.get("fgm", 0)) or 0)
                        ft_a = int(item.get("ftAttempted", item.get("fta", 0)) or 0)
                        ft_m = int(item.get("ftMade", item.get("ftm", 0)) or 0)
                        tpm = int(item.get("threep", item.get("tpm", item.get("threePm", 0))) or 0)
                        tpa = int(item.get("threepAttempted", item.get("tpa", item.get("threePa", 0))) or 0)
                        snap.players.append(
                            PlayerStat(
                                player_id=str(item.get("playerId", p_name)),
                                name=str(p_name),
                                team=team_label,
                                position=str(item.get("position", item.get("pos", ""))),
                                is_starter=bool(item.get("isStarter", False)),
                                points=int(item.get("pts", item.get("points", item.get("totScore", 0))) or 0),
                                rebounds=int(item.get("reb", item.get("rebounds", item.get("totReb", 0))) or 0),
                                off_rebounds=int(item.get("offReb", item.get("oreb", 0)) or 0),
                                assists=int(item.get("ast", item.get("assists", 0)) or 0),
                                steals=int(item.get("stl", item.get("steals", 0)) or 0),
                                blocks=int(item.get("blk", item.get("bs", item.get("blocks", 0))) or 0),
                                turnovers=int(item.get("to", item.get("turnovers", 0)) or 0),
                                three_pm=tpm,
                                three_pa=tpa,
                                fg_missed=max(0, fg_a - fg_m),
                                ft_missed=max(0, ft_a - ft_m),
                                fouls=int(item.get("foul", item.get("pf", 0)) or 0),
                            )
                        )
        return snap

    def _fetch_from_kbl(self, date_str: str) -> Optional[GameSnapshot]:
        compact_date = date_str.replace("-", "")
        list_url = (
            f"{self.KBL_BASE}/match/list?"
            f"fromDate={compact_date}&toDate={compact_date}&seasonGrade=1"
        )
        raw = self._get_json(list_url, self.kbl_headers)
        if not raw:
            return None

        matches = raw if isinstance(raw, list) else raw.get("data", raw.get("list", []))
        if not isinstance(matches, list):
            return None

        target = None
        for m in matches:
            tcode_h = str(m.get("tcodeH", ""))
            tcode_a = str(m.get("tcodeA", ""))
            tname_h = str(m.get("tnameH", m.get("homeTeamName", "")))
            tname_a = str(m.get("tnameA", m.get("awayTeamName", "")))
            if (
                TARGET_KBL_TEAM_CODE in (tcode_h, tcode_a)
                or is_samsung_team(tname_h)
                or is_samsung_team(tname_a)
            ):
                target = m
                break

        if not target:
            return None

        gmkey = str(target.get("gmkey", target.get("gameKey", "")))
        home_team = str(target.get("tnameH", "서울 삼성"))
        away_team = str(target.get("tnameA", "원정팀"))
        is_ended = str(target.get("isEnded", "0")) == "1"

        snap = GameSnapshot(
            game_id=gmkey,
            game_date=date_str,
            start_time=str(target.get("gmTime", "16:30")),
            venue=str(target.get("stadiumName", target.get("place", "잠실학생체육관"))),
            home_team=home_team,
            away_team=away_team,
            status_code="END" if is_ended else "LIVE",
            is_game_finished=is_ended,
            home_score=int(target.get("scoreH", 0) or 0),
            away_score=int(target.get("scoreA", 0) or 0),
        )

        for q_key_h, q_key_a in (
            ("q1H", "q1A"), ("q2H", "q2A"), ("q3H", "q3A"), ("q4H", "q4A"), ("eqH", "eqA")
        ):
            if target.get(q_key_h) is not None and target.get(q_key_a) is not None:
                h_val = int(target.get(q_key_h) or 0)
                a_val = int(target.get(q_key_a) or 0)
                if h_val > 0 or a_val > 0:
                    snap.home_period_scores.append(h_val)
                    snap.away_period_scores.append(a_val)

        return snap


# ==============================================================================
# 7. 경기 상태 추적기
# ==============================================================================

class SamsungGameMonitor:
    def __init__(self, notifier: PushNotifier, persist_state: bool = True) -> None:
        self.notifier = notifier
        self.persist_state = persist_state
        self.sent_events: set[str] = set()
        self.quarter_Player_snapshots: Dict[str, Dict[str, Dict[str, int]]] = {}
        if self.persist_state:
            self._load_state()

    def _load_state(self) -> None:
        try:
            if STATE_FILE_PATH.exists():
                data = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
                self.sent_events = set(data.get("sent_events", []))
                self.quarter_Player_snapshots = data.get("quarter_snapshots", {})
        except Exception:
            pass

    def _save_state(self) -> None:
        if not self.persist_state:
            return
        try:
            payload = {
                "sent_events": sorted(self.sent_events),
                "quarter_snapshots": self.quarter_Player_snapshots,
            }
            STATE_FILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def minutes_until_tipoff(snap: GameSnapshot) -> Optional[float]:
        """경기 시작 시각(KST)까지 남은 시간(분) 반환"""
        try:
            naive_dt = datetime.datetime.strptime(f"{snap.game_date} {snap.start_time}", "%Y-%m-%d %H:%M")
            game_dt = naive_dt.replace(tzinfo=KST)
            return (game_dt - now_kst()).total_seconds() / 60.0
        except Exception:
            return None

    def _is_within_pregame_window(self, snap: GameSnapshot) -> bool:
        mins = self.minutes_until_tipoff(snap)
        if mins is None:
            return True
        return -5.0 <= mins <= (LINEUP_ALERT_MINUTES_BEFORE + 5.0)

    def process_snapshot(self, snap: GameSnapshot, force_lineup_now: bool = False) -> None:
        gid = snap.game_id

        # 1) 경기 시작 30분 전 양 팀 선발 라인업 알림
        lineup_key = f"{gid}:LINEUP_30M"
        if (
            lineup_key not in self.sent_events
            and (snap.home_starters or snap.away_starters)
            and (force_lineup_now or self._is_within_pregame_window(snap))
        ):
            title, body = format_lineup_message(snap)
            self.notifier.send(title, body, tags="basketball,clipboard", priority="default")
            self.sent_events.add(lineup_key)
            self._save_state()

        # 2) 1~3쿼터 종료 시점 알림
        completed_quarters = len(snap.home_period_scores)
        for q in (1, 2, 3):
            q_key = f"{gid}:Q{q}_END"
            is_q_done = (
                (snap.current_period == q and snap.is_period_finished)
                or snap.current_period > q
                or completed_quarters > q
                or snap.is_game_finished
            )
            if is_q_done and q_key not in self.sent_events:
                q_snap = self._prepare_quarter_snapshot(snap, q)
                title, body = format_quarter_end_message(q_snap, quarter=q)
                self.notifier.send(title, body, tags="basketball,loudspeaker", priority="default")
                self.sent_events.add(q_key)
                self._record_cumulative_stats(gid, q, snap.players)
                self._save_state()

        # 3) 4쿼터 종료 및 연장전 분리 알림
        q4_key = f"{gid}:Q4_END"
        final_key = f"{gid}:FINAL_END"

        if len(snap.home_period_scores) >= 4 and len(snap.away_period_scores) >= 4:
            h_q4 = sum(snap.home_period_scores[:4])
            a_q4 = sum(snap.away_period_scores[:4])
            went_to_ot = (h_q4 == a_q4) or len(snap.home_period_scores) > 4 or snap.current_period >= 5
        else:
            went_to_ot = snap.current_period >= 5

        is_q4_done = (
            (snap.current_period == 4 and snap.is_period_finished)
            or snap.current_period >= 5
            or snap.is_game_finished
        )

        if is_q4_done and went_to_ot and q4_key not in self.sent_events:
            q4_snap = self._prepare_quarter_snapshot(snap, 4)
            title, body = format_quarter_end_message(q4_snap, quarter=4)
            self.notifier.send(title, body, tags="fire,basketball", priority="high")
            self.sent_events.add(q4_key)
            self._record_cumulative_stats(gid, 4, snap.players)
            self._save_state()

        if snap.is_game_finished and final_key not in self.sent_events:
            title, body = format_final_result_message(snap, went_to_overtime=went_to_ot)
            self.notifier.send(title, body, tags="trophy,basketball", priority="high")
            self.sent_events.add(q4_key)
            self.sent_events.add(final_key)
            self._save_state()

    def _record_cumulative_stats(self, gid: str, quarter: int, players: List[PlayerStat]) -> None:
        if not players:
            return
        snap_key = f"{gid}:Q{quarter}"
        self.quarter_Player_snapshots[snap_key] = {
            (p.player_id or p.name): {
                "points": p.points,
                "rebounds": p.rebounds,
                "off_rebounds": p.off_rebounds,
                "assists": p.assists,
                "steals": p.steals,
                "blocks": p.blocks,
                "three_pm": p.three_pm,
                "three_pa": p.three_pa,
            }
            for p in players
        }

    def _prepare_quarter_snapshot(self, snap: GameSnapshot, quarter: int) -> GameSnapshot:
        if len(snap.home_period_scores) >= quarter and len(snap.away_period_scores) >= quarter:
            h_score = sum(snap.home_period_scores[:quarter])
            a_score = sum(snap.away_period_scores[:quarter])
            h_periods = snap.home_period_scores[:quarter]
            a_periods = snap.away_period_scores[:quarter]
        else:
            h_score = snap.home_score
            a_score = snap.away_score
            h_periods = list(snap.home_period_scores)
            a_periods = list(snap.away_period_scores)

        if snap.quarter_only_players:
            q_players = snap.quarter_only_players
        else:
            prev_key = f"{snap.game_id}:Q{quarter - 1}"
            prev_map = self.quarter_Player_snapshots.get(prev_key, {})
            q_players = compute_quarter_delta_stats(snap.players, prev_map)

        return GameSnapshot(
            game_id=snap.game_id,
            game_date=snap.game_date,
            start_time=snap.start_time,
            venue=snap.venue,
            home_team=snap.home_team,
            away_team=snap.away_team,
            status_code=f"Q{quarter}_END",
            current_period=quarter,
            is_period_finished=True,
            is_game_finished=False,
            home_score=h_score,
            away_score=a_score,
            home_period_scores=h_periods,
            away_period_scores=a_periods,
            home_starters=snap.home_starters,
            away_starters=snap.away_starters,
            players=snap.players,
            quarter_only_players=q_players,
        )


# ==============================================================================
# 8. 컴퓨터 전원 OFF용 클라우드(GitHub Actions) 스마트 실행 및 자동 생성기
# ==============================================================================

def run_cloud_auto_session(fetcher: KBLDataFetcher, monitor: SamsungGameMonitor, target_date: str) -> None:
    """
    [컴퓨터가 꺼져 있어도 작동하는 무료 클라우드(GitHub Actions) 전용 스마트 세션]
    - 오늘 서울 삼성 경기가 없으면: 1초 만에 즉시 종료 (무료 시간 전혀 소모 안 함!)
    - 오늘 서울 삼성 경기가 있으면: 경기 35분 전까지 대기했다가, 경기 시작 30분 전 라인업부터
      1~4쿼터/연장 종료까지 25초 주기로 실시간 감시한 뒤 경기가 끝나면 자동으로 서버 종료!
    """
    snap = fetcher.fetch_today_samsung_game(target_date=target_date)
    if not snap:
        print(f"ℹ️ [{target_date}] 오늘 예정된 서울 삼성 썬더스 경기가 없어 클라우드 세션을 즉시 종료합니다.")
        return

    print(f"🏀 [{target_date}] 오늘 서울 삼성 경기 발견! ({snap.away_team} vs {snap.home_team}, {snap.start_time} KST)")

    # 만약 경기 시작까지 45분 이상 남아있다면, 이번 스케줄러가 아닌 다음 시간대 스케줄러에 맡기고 종료
    mins_left = monitor.minutes_until_tipoff(snap)
    if mins_left is not None and mins_left > 65.0:
        print(f"⏳ 경기 시작까지 약 {int(mins_left)}분 남아있어 다음 클라우드 트리거에서 감시를 시작합니다.")
        return

    # 최대 4시간 30분 동안 25초 간격으로 실시간 추적
    max_loops = int((4.5 * 3600) / POLL_INTERVAL_SECONDS)
    for _ in range(max_loops):
        current_snap = fetcher.fetch_today_samsung_game(target_date=target_date)
        if current_snap:
            monitor.process_snapshot(current_snap)
            if current_snap.is_game_finished:
                print("✅ 오늘 서울 삼성 경기 최종 종료 알림까지 모두 발송 완료! 클라우드 세션을 종료합니다.")
                return
        time.sleep(POLL_INTERVAL_SECONDS)


def register_windows_autostart(topic: str) -> None:
    script_path = Path(__file__).resolve()
    if platform.system() != "Windows":
        print("ℹ️ 현재 환경은 Windows가 아닙니다.")
        return

    appdata = os.environ.get("APPDATA", "")
    startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_dir.mkdir(parents=True, exist_ok=True)

    python_exe = Path(sys.executable)
    pythonw_exe = python_exe.with_name("pythonw.exe")
    runner = str(pythonw_exe if pythonw_exe.exists() else python_exe)

    vbs_path = startup_dir / "KBL_Samsung_Thunders_Notifier.vbs"
    vbs_content = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run """{runner}"" ""{script_path}"" --topic ""{topic}""", 0, False\n'
    )
    vbs_path.write_text(vbs_content, encoding="utf-8")

    try:
        subprocess.Popen([runner, str(script_path), "--topic", topic], close_fds=True)
    except Exception:
        pass

    print("✅ [윈도우 자동 실행 등록 완료] 경로:", vbs_path)


# ==============================================================================
# 9. 시뮬레이션 데모 (삼성 vs KT 예시 완벽 재현)
# ==============================================================================

def run_demo_simulation(notifier: PushNotifier, include_overtime: bool = True, delay_sec: float = 1.5) -> None:
    mode_str = "연장전(OT) 포함 시나리오" if include_overtime else "정규 4쿼터 종료 시나리오"
    print(f"🚀 [시뮬레이션 시작] 서울 삼성 vs 수원 KT ({mode_str})")
    monitor = SamsungGameMonitor(notifier=notifier, persist_state=False)

    home_starters = ["한호빈(G)", "이관희(G)", "저스틴 구탕(F)", "이규태(F)", "케렘 칸터(C)"]
    away_starters = ["허훈(G)", "한희원(F)", "문정현(F)", "하윤기(C)", "패리스 베스(C)"]

    if include_overtime:
        h_periods = [24, 26, 19, 20, 12]
        a_periods = [22, 21, 25, 21, 6]
    else:
        h_periods = [24, 26, 22, 23]
        a_periods = [22, 21, 23, 21]

    q_player_samples: Dict[int, List[PlayerStat]] = {
        1: [
            PlayerStat("kanter", "칸터", "서울 삼성", "C", points=10, rebounds=4),
            PlayerStat("leegt", "이규태", "서울 삼성", "F", points=6, rebounds=2, three_pm=2),
            PlayerStat("han", "한호빈", "서울 삼성", "G", points=5, assists=3),
            PlayerStat("bass", "베스", "수원 KT", "C", points=9),
            PlayerStat("huh", "허훈", "수원 KT", "G", points=6),
        ],
        2: [
            PlayerStat("kanter", "칸터", "서울 삼성", "C", points=12, rebounds=3),
            PlayerStat("mccullough", "맥컬러", "서울 삼성", "F", points=8, rebounds=3),
            PlayerStat("leekh", "이관희", "서울 삼성", "G", points=6, assists=3),
            PlayerStat("bass", "베스", "수원 KT", "C", points=8),
            PlayerStat("moon", "문정현", "수원 KT", "F", points=5),
        ],
        3: [
            PlayerStat("gutang", "구탕", "서울 삼성", "F", points=7, rebounds=3, assists=2),
            PlayerStat("leegt", "이규태", "서울 삼성", "F", points=6, rebounds=2),
            PlayerStat("kanter", "칸터", "서울 삼성", "C", points=6, rebounds=4),
            PlayerStat("huh", "허훈", "수원 KT", "G", points=10),
            PlayerStat("ha", "하윤기", "수원 KT", "C", points=7),
        ],
        4: [
            PlayerStat("kanter", "칸터", "서울 삼성", "C", points=4, rebounds=2),
            PlayerStat("han", "한호빈", "서울 삼성", "G", points=7, assists=3),
            PlayerStat("gutang", "구탕", "서울 삼성", "F", points=4, rebounds=2, assists=2),
            PlayerStat("bass", "베스", "수원 KT", "C", points=9),
            PlayerStat("moon", "문정현", "수원 KT", "F", points=6),
        ],
    }

    final_players = [
        PlayerStat(
            player_id="kanter", name="칸터", team="서울 삼성", position="C", is_starter=True,
            points=32, rebounds=13, off_rebounds=4, assists=2, steals=1, blocks=2,
            turnovers=2, three_pm=0, three_pa=1, fg_missed=5, ft_missed=1, fouls=3
        ),
        PlayerStat(
            player_id="leegt", name="이규태", team="서울 삼성", position="F", is_starter=True,
            points=15, rebounds=3, off_rebounds=1, assists=1, steals=1, blocks=0,
            turnovers=1, three_pm=3, three_pa=6, fg_missed=4, ft_missed=0, fouls=2
        ),
        PlayerStat(
            player_id="han", name="한호빈", team="서울 삼성", position="G", is_starter=True,
            points=12, rebounds=2, off_rebounds=0, assists=6, steals=1, blocks=0,
            turnovers=1, three_pm=2, three_pa=4, fg_missed=3, ft_missed=0, fouls=2
        ),
        PlayerStat(
            player_id="gutang", name="구탕", team="서울 삼성", position="F", is_starter=True,
            points=11, rebounds=5, off_rebounds=2, assists=4, steals=1, blocks=1,
            turnovers=1, three_pm=1, three_pa=3, fg_missed=3, ft_missed=1, fouls=2
        ),
        PlayerStat(
            player_id="leekh", name="이관희", team="서울 삼성", position="G", is_starter=True,
            points=10, rebounds=2, off_rebounds=0, assists=3, steals=1, blocks=0,
            turnovers=1, three_pm=2, three_pa=5, fg_missed=4, ft_missed=0, fouls=3
        ),
        PlayerStat(
            player_id="bass", name="베스", team="수원 KT", position="C", is_starter=True,
            points=26, rebounds=10, off_rebounds=3, assists=3, steals=1, blocks=1,
            turnovers=4, three_pm=2, three_pa=7, fg_missed=9, ft_missed=2, fouls=3
        ),
    ]

    snap_pre = GameSnapshot(
        game_id="DEMO_20261101_SS_KT",
        game_date="2026-11-01",
        start_time="16:30",
        venue="잠실학생체육관",
        home_team="서울 삼성",
        away_team="수원 KT",
        status_code="BEFORE",
        current_period=0,
        home_starters=home_starters,
        away_starters=away_starters,
    )
    monitor.process_snapshot(snap_pre, force_lineup_now=True)
    time.sleep(delay_sec)

    for q in (1, 2, 3):
        snap_q = GameSnapshot(
            game_id="DEMO_20261101_SS_KT",
            game_date="2026-11-01",
            start_time="16:30",
            venue="잠실학생체육관",
            home_team="서울 삼성",
            away_team="수원 KT",
            status_code=f"Q{q}_END",
            current_period=q,
            is_period_finished=True,
            home_score=sum(h_periods[:q]),
            away_score=sum(a_periods[:q]),
            home_period_scores=h_periods[:q],
            away_period_scores=a_periods[:q],
            home_starters=home_starters,
            away_starters=away_starters,
            quarter_only_players=q_player_samples[q],
        )
        monitor.process_snapshot(snap_q)
        time.sleep(delay_sec)

    if include_overtime:
        snap_q4 = GameSnapshot(
            game_id="DEMO_20261101_SS_KT",
            game_date="2026-11-01",
            start_time="16:30",
            venue="잠실학생체육관",
            home_team="서울 삼성",
            away_team="수원 KT",
            status_code="Q4_END",
            current_period=4,
            is_period_finished=True,
            is_game_finished=False,
            home_score=sum(h_periods[:4]),
            away_score=sum(a_periods[:4]),
            home_period_scores=h_periods[:4],
            away_period_scores=a_periods[:4],
            home_starters=home_starters,
            away_starters=away_starters,
            quarter_only_players=q_player_samples[4],
        )
        monitor.process_snapshot(snap_q4)
        time.sleep(delay_sec)

    snap_final = GameSnapshot(
        game_id="DEMO_20261101_SS_KT",
        game_date="2026-11-01",
        start_time="16:30",
        venue="잠실학생체육관",
        home_team="서울 삼성",
        away_team="수원 KT",
        status_code="END",
        current_period=5 if include_overtime else 4,
        is_period_finished=True,
        is_game_finished=True,
        home_score=sum(h_periods),
        away_score=sum(a_periods),
        home_period_scores=h_periods,
        away_period_scores=a_periods,
        home_starters=home_starters,
        away_starters=away_starters,
        players=final_players,
    )
    monitor.process_snapshot(snap_final)


# ==============================================================================
# 10. 메인 진입점
# ==============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="🏀 서울 삼성 썬더스 KBL 실시간 스마트폰 푸시 알림봇 v3.0"
    )
    parser.add_argument("--topic", type=str, default=NTFY_TOPIC, help="ntfy 스마트폰 푸시 토픽 이름")
    parser.add_argument("--date", type=str, default=None, help="조회 날짜 (YYYY-MM-DD, KST 기준)")
    parser.add_argument(
        "--cloud-auto",
        action="store_true",
        help="[컴퓨터 전원 OFF 클라우드용] 오늘 삼성 경기가 있을 때만 경기 끝날 때까지 감시 후 자동 종료",
    )
    parser.add_argument(
        "--register-windows",
        action="store_true",
        help="윈도우 시작프로그램에 백그라운드 자동 실행 등록",
    )
    parser.add_argument("--once", action="store_true", help="1회 조회 후 종료")
    parser.add_argument("--demo", action="store_true", help="정규 4쿼터 종료 시나리오 푸시 테스트")
    parser.add_argument("--demo-ot", action="store_true", help="연장전(OT) 시나리오 푸시 테스트")
    parser.add_argument("--dry-run", action="store_true", help="콘솔 출력만 수행")
    args = parser.parse_args()

    if args.register_windows:
        register_windows_autostart(topic=args.topic)
        return

    notifier = PushNotifier(ntfy_topic=args.topic, dry_run=args.dry_run)

    if args.demo or args.demo_ot:
        run_demo_simulation(
            notifier=notifier,
            include_overtime=bool(args.demo_ot),
            delay_sec=0.2 if args.dry_run else 1.5,
        )
        return

    fetcher = KBLDataFetcher()
    monitor = SamsungGameMonitor(notifier=notifier, persist_state=True)
    today_str = args.date or now_kst().strftime("%Y-%m-%d")

    if args.cloud_auto:
        run_cloud_auto_session(fetcher=fetcher, monitor=monitor, target_date=today_str)
        return

    if args.once:
        snap = fetcher.fetch_today_samsung_game(target_date=today_str)
        if snap:
            monitor.process_snapshot(snap)
        return

    while True:
        current_date = args.date or now_kst().strftime("%Y-%m-%d")
        snap = fetcher.fetch_today_samsung_game(target_date=current_date)
        if snap:
            monitor.process_snapshot(snap)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()