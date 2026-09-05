/**
 * Ajedrez Escolar - Stockfish Interactive Analysis Viewer
 */

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

class AnalysisApp {
    constructor() {
        this.boardEl = document.getElementById('chessboard');
        this.moveAnalyses = MOVE_ANALYSES || [];
        this.currentPly = 0;
        this.currentMode = 'ANALYSIS'; // 'ANALYSIS', 'TRAINING', 'COMPETITION'
        this.pollInterval = null;

        this.initEvents();

        if (JOB_INITIAL_STATUS === 'PENDING' || JOB_INITIAL_STATUS === 'PROCESSING') {
            this.startPollingStatus();
        } else {
            this.render();
        }
    }

    initEvents() {
        document.getElementById('btn-first')?.addEventListener('click', () => this.goToPly(0));
        document.getElementById('btn-prev')?.addEventListener('click', () => this.goToPly(this.currentPly - 1));
        document.getElementById('btn-next')?.addEventListener('click', () => this.goToPly(this.currentPly + 1));
        document.getElementById('btn-last')?.addEventListener('click', () => this.goToPly(this.moveAnalyses.length));

        // Keyboard arrow navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') this.goToPly(this.currentPly - 1);
            if (e.key === 'ArrowRight') this.goToPly(this.currentPly + 1);
        });

        // Copy FEN button
        document.getElementById('btn-copy-fen')?.addEventListener('click', () => {
            const fenInput = document.getElementById('fen-input');
            if (fenInput && fenInput.value) {
                navigator.clipboard.writeText(fenInput.value);
                alert('FEN copiado al portapapeles.');
            }
        });

        // Mode switchers
        document.getElementById('mode-analysis-btn')?.addEventListener('click', () => this.setMode('ANALYSIS'));
        document.getElementById('mode-training-btn')?.addEventListener('click', () => this.setMode('TRAINING'));
        document.getElementById('mode-competition-btn')?.addEventListener('click', () => this.setMode('COMPETITION'));
    }

    setMode(mode) {
        this.currentMode = mode;
        ['analysis', 'training', 'competition'].forEach(m => {
            const btn = document.getElementById(`mode-${m}-btn`);
            if (btn) {
                btn.className = (m === mode.toLowerCase()) ? 'btn btn-primary' : 'btn btn-secondary';
            }
        });
        this.render();
    }

    startPollingStatus() {
        this.pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/analysis/job/${JOB_ID}/status/`);
                const data = await res.json();

                const progressCard = document.getElementById('job-progress-card');
                const progressBar = document.getElementById('job-progress-bar');
                const statusText = document.getElementById('job-status-text');

                if (progressBar) progressBar.style.width = `${data.progress_percent}%`;
                if (statusText) statusText.textContent = `Estado: ${data.status} (${data.progress_percent}%)`;

                if (data.status === 'COMPLETED' || data.status === 'FAILED') {
                    clearInterval(this.pollInterval);
                    if (data.status === 'COMPLETED') {
                        window.location.reload();
                    } else {
                        alert(`El análisis falló: ${data.error_message}`);
                    }
                }
            } catch (err) {
                console.error(err);
            }
        }, 1500);
    }

    goToPly(ply) {
        this.currentPly = Math.max(0, Math.min(ply, this.moveAnalyses.length));
        this.render();
    }

    getCurrentFen() {
        if (this.currentPly === 0 || this.moveAnalyses.length === 0) {
            return STARTING_FEN;
        }
        return this.moveAnalyses[this.currentPly - 1].fen_after;
    }

    render() {
        const fen = this.getCurrentFen();
        this.renderBoard(fen);
        this.updateFenInput(fen);
        this.updateEvaluation();
        this.renderMoveList();
    }

    renderBoard(fen) {
        if (!this.boardEl || !window.ChessUI) return;
        this.boardEl.innerHTML = '';
        const grid = ChessUI.parseFenPlacement(fen);

        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                const fileChar = String.fromCharCode(97 + c);
                const rankNum = 8 - r;
                const squareName = `${fileChar}${rankNum}`;
                const squareEl = document.createElement('div');
                squareEl.className = `square ${(r + c) % 2 === 0 ? 'light' : 'dark'}`;
                squareEl.dataset.square = squareName;

                ChessUI.appendCoordinates(squareEl, { col: c, row: r, fileChar, rankNum });

                const piece = grid[r][c];
                if (piece) {
                    squareEl.appendChild(ChessUI.createPieceElement(piece));
                }
                this.boardEl.appendChild(squareEl);
            }
        }

        if (this.currentPly > 0 && this.moveAnalyses[this.currentPly - 1]) {
            ChessUI.applyLastMove(this.boardEl, this.moveAnalyses[this.currentPly - 1].move_uci);
        }
    }

    updateFenInput(fen) {
        const input = document.getElementById('fen-input');
        if (input) input.value = fen;
    }

    updateEvaluation() {
        const evalHeader = document.getElementById('eval-header-text');
        const bestMoveText = document.getElementById('best-move-text');
        const pvLineText = document.getElementById('pv-line-text');
        const qualityBadge = document.getElementById('move-quality-badge');
        const whiteBar = document.getElementById('eval-bar-white');
        const blackBar = document.getElementById('eval-bar-black');

        // Coach UI elements
        const coachAvatar = document.getElementById('coach-avatar');
        const coachTitle = document.getElementById('coach-title');
        const coachThemeBadge = document.getElementById('coach-theme-badge');
        const coachMessageText = document.getElementById('coach-message-text');
        const coachExplanationText = document.getElementById('coach-explanation-text');
        const coachHintBox = document.getElementById('coach-hint-box');
        const coachHintText = document.getElementById('coach-hint-text');
        const btnToggleHint = document.getElementById('btn-toggle-hint');

        if (this.currentMode === 'COMPETITION') {
            if (evalHeader) evalHeader.textContent = 'Evaluación deshabilitada';
            if (bestMoveText) bestMoveText.textContent = 'Oculto';
            if (pvLineText) pvLineText.textContent = 'Oculto en modo Competición';
            if (qualityBadge) qualityBadge.textContent = 'Oculto';
            if (whiteBar) whiteBar.style.height = '50%';
            if (blackBar) blackBar.style.height = '50%';
            return;
        }

        const currentAnalysis = (this.currentPly > 0 && this.moveAnalyses.length >= this.currentPly)
            ? this.moveAnalyses[this.currentPly - 1]
            : null;

        let scoreCp = currentAnalysis ? currentAnalysis.score_cp : 0;
        let mateIn = currentAnalysis ? currentAnalysis.mate_in : null;

        // Header text formatting
        let evalStr = '0.00';
        if (mateIn !== null && mateIn !== undefined) {
            evalStr = `Mate en ${mateIn}`;
        } else if (scoreCp !== null && scoreCp !== undefined) {
            evalStr = (scoreCp >= 0 ? `+${(scoreCp/100).toFixed(2)}` : `${(scoreCp/100).toFixed(2)}`);
        }
        if (evalHeader) evalHeader.textContent = `Evaluación: ${evalStr}`;

        // Best move & PV formatting
        if (this.currentMode === 'ANALYSIS') {
            if (bestMoveText) bestMoveText.textContent = currentAnalysis?.position_analysis__best_move_san || '--';
            if (pvLineText) pvLineText.textContent = (currentAnalysis?.position_analysis__pv_san || []).join(' ') || '--';
        } else {
            // Training mode: hints hidden unless clicked
            if (bestMoveText) bestMoveText.textContent = '💡 Disponible como Pista';
            if (pvLineText) pvLineText.textContent = 'Oculto en modo Entrenamiento';
        }

        // Spanish Quality Badges Mapping
        const SPANISH_QUALITY_MAP = {
            'BOOK': { label: '📚 LIBRO', bg: 'rgba(59, 130, 246, 0.3)' },
            'BRILLIANT': { label: '💎 BRILLANTE', bg: 'rgba(168, 85, 247, 0.35)' },
            'BEST': { label: '🎯 MEJOR', bg: 'rgba(16, 185, 129, 0.35)' },
            'EXCELLENT': { label: '👍 EXCELENTE', bg: 'rgba(52, 211, 153, 0.3)' },
            'GOOD': { label: '✓ BUENA', bg: 'rgba(96, 165, 250, 0.3)' },
            'INACCURACY': { label: '⚠️ INEXACTITUD', bg: 'rgba(245, 158, 11, 0.3)' },
            'MISTAKE': { label: '❌ ERROR', bg: 'rgba(249, 115, 22, 0.3)' },
            'BLUNDER': { label: '💥 GRAN ERROR', bg: 'rgba(239, 68, 68, 0.35)' },
            'MISS': { label: '❓ OPORTUNIDAD PERDIDA', bg: 'rgba(236, 72, 153, 0.3)' }
        };

        if (qualityBadge) {
            const qualityCode = currentAnalysis?.quality || '--';
            const mapped = SPANISH_QUALITY_MAP[qualityCode] || { label: qualityCode, bg: 'rgba(255,255,255,0.1)' };
            qualityBadge.textContent = mapped.label;
            qualityBadge.style.background = mapped.bg;
        }

        // Update Coach UI Card
        const reviewData = currentAnalysis?.review_data || {};
        if (currentAnalysis && reviewData) {
            const emotion = reviewData.coach_emotion || 'NEUTRAL';
            let avatarEmoji = '🎓';
            if (emotion === 'EXCITED') avatarEmoji = '🌟';
            if (emotion === 'HAPPY') avatarEmoji = '🎯';
            if (emotion === 'WARNING') avatarEmoji = '⚠️';
            if (emotion === 'SURPRISED') avatarEmoji = '😮';

            if (coachAvatar) coachAvatar.textContent = avatarEmoji;
            if (coachTitle) coachTitle.textContent = `Entrenador de Ajedrez`;
            if (coachThemeBadge) coachThemeBadge.textContent = reviewData.tactical_theme || 'Posicional';
            if (coachMessageText) coachMessageText.textContent = reviewData.coach_message || 'Observa la posición.';
            if (coachExplanationText) coachExplanationText.textContent = reviewData.explanation_text || 'Análisis en progreso.';

            const hints = reviewData.hints || [];
            if (hints.length > 0) {
                if (btnToggleHint) {
                    btnToggleHint.style.display = 'block';
                    btnToggleHint.onclick = () => {
                        if (coachHintBox) {
                            coachHintBox.style.display = coachHintBox.style.display === 'none' ? 'block' : 'none';
                            if (coachHintText) coachHintText.textContent = hints[0];
                        }
                    };
                }
            } else {
                if (btnToggleHint) btnToggleHint.style.display = 'none';
                if (coachHintBox) coachHintBox.style.display = 'none';
            }

            // Apply square highlights on board if present
            if (reviewData.highlighted_squares) {
                reviewData.highlighted_squares.forEach(hs => {
                    const sqEl = this.boardEl?.querySelector(`[data-square="${hs.square}"]`);
                    if (sqEl) {
                        sqEl.style.boxShadow = `inset 0 0 0 4px ${hs.color === 'red' ? '#ef4444' : '#f59e0b'}`;
                    }
                });
            }
        }

        // Evaluation gauge bar (0% to 100% white height)
        let whiteHeightPercent = 50;
        if (mateIn !== null && mateIn !== undefined) {
            whiteHeightPercent = (mateIn > 0) ? 100 : 0;
        } else if (scoreCp !== null && scoreCp !== undefined) {
            // Sigmoid formula for smooth evaluation gauge
            const val = scoreCp / 100.0;
            whiteHeightPercent = 50 + (50 * (2 / (1 + Math.exp(-0.4 * val)) - 1));
        }

        whiteHeightPercent = Math.max(5, Math.min(95, whiteHeightPercent));
        if (whiteBar) whiteBar.style.height = `${whiteHeightPercent}%`;
        if (blackBar) blackBar.style.height = `${100 - whiteHeightPercent}%`;
    }

    renderMoveList() {
        const historyEl = document.getElementById('move-history');
        if (!historyEl) return;
        historyEl.innerHTML = '';

        for (let i = 0; i < this.moveAnalyses.length; i += 2) {
            const moveNum = Math.floor(i / 2) + 1;
            const whiteMoveObj = this.moveAnalyses[i];
            const blackMoveObj = this.moveAnalyses[i + 1];

            const row = document.createElement('div');
            row.className = 'move-row';
            if (this.currentPly === i + 1 || this.currentPly === i + 2) {
                row.classList.add('current');
            }
            row.style.cursor = 'pointer';

            const whiteClass = (this.currentPly === i + 1) ? ' is-last' : '';
            const blackClass = (this.currentPly === i + 2) ? ' is-last' : '';

            row.innerHTML = `
                <span class="move-num">${moveNum}.</span>
                <span class="move-san${whiteClass}" data-ply="${i + 1}">${whiteMoveObj ? whiteMoveObj.move_san : ''}</span>
                <span class="move-san${blackClass}" data-ply="${i + 2}">${blackMoveObj ? blackMoveObj.move_san : ''}</span>
            `;

            row.querySelectorAll('span[data-ply]').forEach(span => {
                span.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const targetPly = parseInt(e.currentTarget.getAttribute('data-ply'));
                    if (!isNaN(targetPly)) this.goToPly(targetPly);
                });
            });

            historyEl.appendChild(row);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.analysisApp = new AnalysisApp();
});

