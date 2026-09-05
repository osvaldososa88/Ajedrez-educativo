/**
 * Ajedrez Escolar - Real-Time Interactive Board & WebSocket Client
 * Move legality is server-authoritative (python-chess). This file only renders and sends UCI.
 */

class ChessboardApp {
    constructor() {
        this.boardEl = document.getElementById('chessboard');
        this.selectedSquare = null;
        this.gameState = null;
        this.pendingMove = null;
        this.timerInterval = null;
        this.lastAnimatedUci = null;

        // Initialize chat if available
        if (window.initChat) {
            window.initChat();
        }

        if (window.ChessUI) {
            const promoColor = (typeof PLAYER_COLOR !== 'undefined' && PLAYER_COLOR === 'black') ? 'black' : 'white';
            ChessUI.paintPromotionChoices(document.getElementById('promotion-modal'), promoColor);
        }

        this.initWebSocket();
        this.initEvents();
    }

    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/game/${GAME_ID}/`;

        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            const statusEl = document.getElementById('connection-status');
            if (statusEl) {
                statusEl.textContent = 'En línea';
                statusEl.classList.add('online');
                statusEl.classList.remove('offline');
            }
        };

        this.socket.onclose = () => {
            const statusEl = document.getElementById('connection-status');
            if (statusEl) {
                statusEl.textContent = 'Desconectado';
                statusEl.classList.add('offline');
                statusEl.classList.remove('online');
            }
        };

        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'init_state' || data.type === 'game_update') {
                this.updateGameState(data.state);
            } else if (data.type === 'error') {
                alert(data.message);
            } else if (data.type === 'draw_offer') {
                if (data.offered_by !== USER_NAME) {
                    const banner = document.getElementById('draw-offer-banner');
                    const textEl = document.getElementById('draw-offer-text');
                    if (banner && textEl) {
                        textEl.textContent = `${data.offered_by} te ofrece tablas`;
                        banner.style.display = 'block';
                    }
                }
            } else if (data.type === 'chat_message') {
                if (window.handleChatMessage) window.handleChatMessage(data);
            } else if (data.type === 'chat_history') {
                if (window.handleChatHistory) window.handleChatHistory(data);
            }
        };
    }

    initEvents() {
        const resignBtn = document.getElementById('btn-resign');
        if (resignBtn) {
            resignBtn.addEventListener('click', () => {
                if (confirm('¿Estás seguro de que deseas abandonar la partida?')) {
                    this.socket.send(JSON.stringify({ type: 'resign' }));
                }
            });
        }

        const drawBtn = document.getElementById('btn-draw');
        if (drawBtn) {
            drawBtn.addEventListener('click', () => {
                this.socket.send(JSON.stringify({ type: 'offer_draw' }));
                alert('Oferta de tablas enviada al oponente.');
            });
        }

        const acceptDrawBanner = document.getElementById('btn-accept-draw-banner');
        if (acceptDrawBanner) {
            acceptDrawBanner.addEventListener('click', () => {
                this.socket.send(JSON.stringify({ type: 'accept_draw' }));
                const banner = document.getElementById('draw-offer-banner');
                if (banner) banner.style.display = 'none';
            });
        }

        const declineDrawBanner = document.getElementById('btn-decline-draw-banner');
        if (declineDrawBanner) {
            declineDrawBanner.addEventListener('click', () => {
                const banner = document.getElementById('draw-offer-banner');
                if (banner) banner.style.display = 'none';
            });
        }

        document.querySelectorAll('.promotion-choice').forEach(choice => {
            choice.addEventListener('click', (e) => {
                const piece = e.currentTarget.getAttribute('data-piece');
                if (this.pendingMove) {
                    const uciWithPromotion = `${this.pendingMove.from}${this.pendingMove.to}${piece}`;
                    this.sendMove(uciWithPromotion);
                    this.pendingMove = null;
                    document.getElementById('promotion-modal').style.display = 'none';
                }
            });
        });
    }

    lastMoveUci(state) {
        if (state.last_move && state.last_move.uci) return state.last_move.uci;
        const history = state.moves_history || [];
        if (!history.length) return null;
        return history[history.length - 1].uci || null;
    }

    isCheckmate(state) {
        const reason = (state.finish_reason || '').toString().toLowerCase();
        return state.status === 'FINISHED' && (reason.includes('mate') || reason.includes('jaque mate'));
    }

    updateGameState(state) {
        const prevFen = this.gameState && this.gameState.fen;
        this.gameState = state;
        this.renderBoard();

        const uci = this.lastMoveUci(state);
        if (window.ChessUI && prevFen && state.fen && prevFen !== state.fen && uci && uci !== this.lastAnimatedUci) {
            ChessUI.animateMovedPiece(this.boardEl, uci);
            this.lastAnimatedUci = uci;
        }

        this.updateSidebar();
        this.updateTimers();

        // Update chat state based on game status
        if (window.updateChatState) window.updateChatState(state);

        if (state.status === 'FINISHED' || state.status === 'ABANDONED') {
            this.showGameOverModal(state);
        }
    }

    renderBoard() {
        if (!this.boardEl || !this.gameState || !window.ChessUI) return;

        this.boardEl.innerHTML = '';
        const grid = ChessUI.parseFenPlacement(this.gameState.fen);
        const isFlipped = (PLAYER_COLOR === 'black');

        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                const rankIdx = isFlipped ? 7 - r : r;
                const fileIdx = isFlipped ? 7 - c : c;

                const fileChar = String.fromCharCode(97 + fileIdx);
                const rankNum = 8 - rankIdx;
                const squareName = `${fileChar}${rankNum}`;

                const squareEl = document.createElement('div');
                const isLight = (rankIdx + fileIdx) % 2 === 0;
                squareEl.className = `square ${isLight ? 'light' : 'dark'}`;
                squareEl.dataset.square = squareName;

                ChessUI.appendCoordinates(squareEl, {
                    col: c,
                    row: r,
                    fileChar,
                    rankNum
                });

                const piece = grid[rankIdx][fileIdx];
                if (piece) {
                    squareEl.appendChild(ChessUI.createPieceElement(piece, {
                        onDragStart: (e) => {
                            if (this.gameState && this.gameState.status === 'IN_PROGRESS') {
                                e.dataTransfer.setData('text/plain', squareName);
                                e.dataTransfer.effectAllowed = 'move';
                                this.selectedSquare = squareName;
                                // Highlight legal moves immediately on drag start
                                setTimeout(() => this.renderBoard(), 0);
                            }
                        }
                    }));
                }

                squareEl.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                });

                squareEl.addEventListener('drop', (e) => {
                    e.preventDefault();
                    const fromSq = e.dataTransfer.getData('text/plain') || this.selectedSquare;
                    if (fromSq && fromSq !== squareName) {
                        this.selectedSquare = fromSq;
                        this.handleSquareClick(squareName);
                    }
                });

                squareEl.addEventListener('click', () => this.handleSquareClick(squareName));
                this.boardEl.appendChild(squareEl);
            }
        }

        ChessUI.applyLastMove(this.boardEl, this.lastMoveUci(this.gameState));
        ChessUI.applyCheck(this.boardEl, grid, this.gameState.fen, {
            isCheck: !!this.gameState.is_check,
            isCheckmate: this.isCheckmate(this.gameState)
        });

        if (this.selectedSquare) {
            const sqEl = this.boardEl.querySelector(`[data-square="${this.selectedSquare}"]`);
            if (sqEl) sqEl.classList.add('selected');
            ChessUI.applyLegalHints(
                this.boardEl,
                this.selectedSquare,
                this.gameState.legal_moves || [],
                grid
            );
        }
    }

    handleSquareClick(squareName) {
        if (!this.gameState || this.gameState.status !== 'IN_PROGRESS') return;

        const isMyTurn = (PLAYER_COLOR === 'white' && this.gameState.turn === 'WHITE') ||
                         (PLAYER_COLOR === 'black' && this.gameState.turn === 'BLACK');

        if (!isMyTurn) return;

        if (!this.selectedSquare) {
            const legalFromThisSq = this.gameState.legal_moves.filter(m => m.from === squareName);
            if (legalFromThisSq.length > 0) {
                this.selectedSquare = squareName;
                this.renderBoard();
            }
        } else {
            if (this.selectedSquare === squareName) {
                this.selectedSquare = null;
                this.renderBoard();
                return;
            }

            const matchingMove = this.gameState.legal_moves.find(
                m => m.from === this.selectedSquare && m.to === squareName
            );

            if (matchingMove) {
                const isPawnPromotion = matchingMove.promotion !== null ||
                    (matchingMove.uci.length === 5);

                if (isPawnPromotion && !matchingMove.uci.slice(4)) {
                    this.pendingMove = { from: this.selectedSquare, to: squareName };
                    if (window.ChessUI) {
                        ChessUI.paintPromotionChoices(
                            document.getElementById('promotion-modal'),
                            PLAYER_COLOR === 'black' ? 'black' : 'white'
                        );
                    }
                    document.getElementById('promotion-modal').style.display = 'flex';
                } else {
                    this.sendMove(matchingMove.uci);
                }
                this.selectedSquare = null;
            } else {
                const legalFromNewSq = this.gameState.legal_moves.filter(m => m.from === squareName);
                if (legalFromNewSq.length > 0) {
                    this.selectedSquare = squareName;
                    this.renderBoard();
                } else {
                    this.selectedSquare = null;
                    this.renderBoard();
                }
            }
        }
    }

    sendMove(uciStr) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'make_move',
                uci: uciStr
            }));
        }
    }

    updateSidebar() {
        const turnEl = document.getElementById('turn-indicator');
        if (turnEl) {
            turnEl.textContent = (this.gameState.turn === 'WHITE') ? 'Blancas' : 'Negras';
        }

        const checkAlert = document.getElementById('check-alert');
        if (checkAlert) {
            const mate = this.isCheckmate(this.gameState);
            if (mate) {
                checkAlert.textContent = 'Jaque mate';
                checkAlert.classList.add('visible');
                checkAlert.style.display = 'block';
            } else if (this.gameState.is_check) {
                checkAlert.textContent = 'Jaque';
                checkAlert.classList.add('visible');
                checkAlert.style.display = 'block';
            } else {
                checkAlert.classList.remove('visible');
                checkAlert.style.display = 'none';
            }
        }

        const historyEl = document.getElementById('move-history');
        if (historyEl) {
            historyEl.innerHTML = '';
            const history = this.gameState.moves_history || [];
            for (let i = 0; i < history.length; i += 2) {
                const moveNum = Math.floor(i / 2) + 1;
                const whiteMove = history[i] ? history[i].san : '';
                const blackMove = history[i + 1] ? history[i + 1].san : '';
                const lastIndex = history.length - 1;

                const row = document.createElement('div');
                row.className = 'move-row';
                if (i === lastIndex || i + 1 === lastIndex) row.classList.add('current');
                row.innerHTML = `
                    <span class="move-num">${moveNum}.</span>
                    <span class="move-san${i === lastIndex ? ' is-last' : ''}">${whiteMove}</span>
                    <span class="move-san${i + 1 === lastIndex ? ' is-last' : ''}">${blackMove}</span>
                `;
                historyEl.appendChild(row);
            }
            historyEl.scrollTop = historyEl.scrollHeight;
        }
    }

    updateTimers() {
        if (this.timerInterval) clearInterval(this.timerInterval);

        const formatTime = (ms) => {
            const totalSec = Math.max(0, Math.floor(ms / 1000));
            const min = Math.floor(totalSec / 60);
            const sec = totalSec % 60;
            return `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
        };

        const isWhite = (PLAYER_COLOR === 'white');
        const bottomTimer = document.getElementById('bottom-timer');
        const topTimer = document.getElementById('top-timer');

        if (bottomTimer && topTimer) {
            let whiteTime = this.gameState.white_time_left_ms;
            let blackTime = this.gameState.black_time_left_ms;

            const paintClock = (el, ms, active) => {
                el.textContent = formatTime(ms);
                el.classList.toggle('active', active);
                el.classList.toggle('low', ms <= 20000);
            };

            const renderClocks = () => {
                // Only show active state if the clock has started
                const clockRunning = !!this.gameState.clock_started;
                const whiteActive = clockRunning && this.gameState.turn === 'WHITE';
                const blackActive = clockRunning && this.gameState.turn === 'BLACK';
                paintClock(bottomTimer, isWhite ? whiteTime : blackTime, isWhite ? whiteActive : blackActive);
                paintClock(topTimer, isWhite ? blackTime : whiteTime, isWhite ? blackActive : whiteActive);
            };

            renderClocks();

            // Only tick the clock locally when the server has confirmed it started
            if (this.gameState.status === 'IN_PROGRESS' && this.gameState.clock_started) {
                this.timerInterval = setInterval(() => {
                    if (this.gameState.turn === 'WHITE') {
                        whiteTime = Math.max(0, whiteTime - 1000);
                    } else {
                        blackTime = Math.max(0, blackTime - 1000);
                    }
                    renderClocks();
                }, 1000);
            }
        }
    }

    showGameOverModal(state) {
        const modal = document.getElementById('game-over-modal');
        const titleEl = document.getElementById('game-over-title');
        const reasonEl = document.getElementById('game-over-reason');

        if (!modal) return;

        let resultText = 'Fin de la partida';
        if (state.winner === 'WHITE') {
            resultText = 'Victoria de las blancas';
        } else if (state.winner === 'BLACK') {
            resultText = 'Victoria de las negras';
        } else if (state.winner === 'DRAW') {
            resultText = 'Tablas';
        }

        titleEl.textContent = resultText;
        reasonEl.textContent = `Motivo: ${state.finish_reason || 'Finalizada'}`;
        modal.style.display = 'flex';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.chessApp = new ChessboardApp();
});
