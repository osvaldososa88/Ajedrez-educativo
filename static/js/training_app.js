/**
 * Ajedrez Escolar - Puzzle / Training Solver
 * Client-side interactive board for solving training exercises.
 * Move legality for the student is validated authoritatively by the server
 * (submit_puzzle_move_api); this client only builds the UCI string and
 * renders the resulting position using chess.js-free FEN parsing.
 */

class PuzzleSolverApp {
    constructor() {
        this.boardEl = document.getElementById('chessboard');
        if (!this.boardEl) return;

        this.fen = PUZZLE_FEN;
        this.fenHistory = [PUZZLE_FEN];
        this.historyIndex = 0;
        this.sideToMove = PUZZLE_SIDE_TO_MOVE; // 'white' or 'black'
        this.puzzleType = PUZZLE_TYPE || 'SEQUENCE'; // 'SEQUENCE' or 'OBJECTIVE'
        this.plyIndex = 0;
        this.attemptsCount = 0;
        this.hintsUsed = 0;
        this.startTime = Date.now();
        this.selectedSquare = null;
        this.solved = false;
        this.pendingMove = null;
        this.legalMoves = null;
        this.attemptId = null;  // Will be set after first move

        this.renderBoard();
        this.initEvents();
        if (window.ChessUI) {
            ChessUI.paintPromotionChoices(
                document.getElementById('promotion-modal'),
                this.sideToMove === 'black' ? 'black' : 'white'
            );
            ChessUI.createBoardNavigator(document.getElementById('board-nav-container'), {
                onNavigate: (action) => this.handleNavigate(action)
            });
        }
        // Fetch legal moves for the initial position
        this.fetchLegalMoves();
        // OBJETIVO: reanudar desde el estado REAL del intento en curso para
        // evitar desincronización (jugadas ilegales). Los puzzles SEQUENCE
        // no tienen estado de sesión y siguen usando el FEN inicial.
        if (this.puzzleType === 'OBJECTIVE' && typeof STATE_URL !== 'undefined') {
            this.fetchObjectiveState();
        }
    }

    pushFen(newFen) {
        if (!this.fenHistory) this.fenHistory = [];
        if (!newFen) return;
        if (this.fenHistory.length === 0 || this.fenHistory[this.fenHistory.length - 1] !== newFen) {
            this.fenHistory.push(newFen);
        }
        this.historyIndex = this.fenHistory.length - 1;
        this.fen = newFen;
    }

    handleNavigate(action) {
        if (!this.fenHistory || this.fenHistory.length === 0) return;
        if (action === 'first') {
            this.historyIndex = 0;
        } else if (action === 'prev') {
            this.historyIndex = Math.max(0, this.historyIndex - 1);
        } else if (action === 'next') {
            this.historyIndex = Math.min(this.fenHistory.length - 1, this.historyIndex + 1);
        } else if (action === 'last') {
            this.historyIndex = this.fenHistory.length - 1;
        }
        this.renderBoard();
    }

    fetchObjectiveState() {
        fetch(STATE_URL, {
            method: 'GET',
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
            .then(res => res.json())
            .then(data => {
                if (data.error) return;
                if (data.fen) {
                    this.pushFen(data.fen);
                }
                this.attemptId = data.attempt_id || null;
                this.plyIndex = data.human_moves || 0;
                const counter = document.getElementById('move-counter');
                if (counter) {
                    const maxStr = data.max_moves && data.max_moves > 0 ? data.max_moves : '∞';
                    counter.textContent = `Movimientos: ${data.human_moves || 0} / ${maxStr}`;
                }
                this.renderBoard();
                this.fetchLegalMoves();
            })
            .catch(() => { /* El tablero inicial sigue siendo una posición válida */ });
    }

    parseFen(fen) {
        return window.ChessUI ? ChessUI.parseFenPlacement(fen) : [];
    }

    renderBoard() {
        this.boardEl.innerHTML = '';
        if (!window.ChessUI) return;
        const currentFen = (this.fenHistory && this.fenHistory[this.historyIndex]) ? this.fenHistory[this.historyIndex] : this.fen;
        const grid = this.parseFen(currentFen);
        const isFlipped = (this.sideToMove === 'black');
        const isBrowsingHistory = (this.fenHistory && this.historyIndex < this.fenHistory.length - 1);

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
                            if (!this.solved && !isBrowsingHistory) {
                                e.dataTransfer.setData('text/plain', squareName);
                                e.dataTransfer.effectAllowed = 'move';
                                this.selectedSquare = squareName;
                                setTimeout(() => this.renderBoard(), 0);
                            }
                        }
                    }));
                }

                if (!isBrowsingHistory) {
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
                }
                this.boardEl.appendChild(squareEl);
            }
        }

        if (this.selectedSquare && !isBrowsingHistory) {
            const sqEl = this.boardEl.querySelector(`[data-square="${this.selectedSquare}"]`);
            if (sqEl) sqEl.classList.add('selected');
        }
        if (!isBrowsingHistory) {
            this.showLegalIndicators();
        }
    }

    showLegalIndicators() {
        if (!window.ChessUI || !this.boardEl) return;
        // Clear previous indicators (but not selected square)
        this.boardEl.querySelectorAll('.legal-move, .legal-capture').forEach(el => {
            el.classList.remove('legal-move', 'legal-capture');
        });
        if (!this.selectedSquare || !this.legalMoves || this.solved) return;

        const legalMovesForSquare = this.legalMoves.filter(m => m.from === this.selectedSquare);
        if (legalMovesForSquare.length === 0) return;

        const currentFen = (this.fenHistory && this.historyIndex < this.fenHistory.length) ? this.fenHistory[this.historyIndex] : this.fen;
        const grid = this.parseFen(currentFen);

        legalMovesForSquare.forEach(m => {
            const targetEl = this.boardEl.querySelector(`[data-square="${m.to}"]`);
            if (!targetEl) return;
            // Check if target square has a piece (for capture indicator)
            const file = m.to.charCodeAt(0) - 97;
            const rank = 8 - parseInt(m.to[1], 10);
            const occupant = grid[rank] && grid[rank][file];
            if (occupant) {
                targetEl.classList.add('legal-capture');
            } else {
                targetEl.classList.add('legal-move');
            }
        });
    }

    async fetchLegalMoves() {
        if (!window.ChessUI || !this.boardEl) return;
        try {
            const currentFen = (this.fenHistory && this.historyIndex < this.fenHistory.length) ? this.fenHistory[this.historyIndex] : this.fen;
            const url = `${LEGAL_MOVES_URL}${LEGAL_MOVES_URL.includes('?') ? '&' : '?'}ply_index=${this.plyIndex}&fen=${encodeURIComponent(currentFen)}`;
            const resp = await fetch(url, {
                method: 'GET',
                headers: { 'X-CSRFToken': getCookie('csrftoken') }
            });
            if (resp.ok) {
                const data = await resp.json();
                this.legalMoves = data.moves || [];
                this.showLegalIndicators();
            }
        } catch (e) {
            console.debug('Could not fetch legal moves:', e);
        }
    }

    handleSquareClick(squareName) {
        if (this.solved) return;

        if (!this.selectedSquare) {
            // First selection - select a piece and show its legal moves
            this.selectedSquare = squareName;
            this.fetchLegalMoves();
            this.renderBoard();
            return;
        }

        if (this.selectedSquare === squareName) {
            // Deselect - clear legal indicators
            this.selectedSquare = null;
            this.legalMoves = null;
            this.renderBoard();
            return;
        }

        const fromSq = this.selectedSquare;
        this.selectedSquare = null;
        this.legalMoves = null;

        // Detect promotion (pawn reaching last rank)
        const isPromotionRank = squareName.endsWith('8') || squareName.endsWith('1');
        const pieceAtFrom = this.getPieceAt(fromSq);
        const isPawn = pieceAtFrom && pieceAtFrom.toLowerCase() === 'p';

        if (isPawn && isPromotionRank) {
            this.pendingMove = { from: fromSq, to: squareName };
            const modal = document.getElementById('promotion-modal');
            if (modal) modal.style.display = 'flex';
            return;
        }

        this.submitMove(`${fromSq}${squareName}`);
    }

    getPieceAt(squareName) {
        const file = squareName.charCodeAt(0) - 97;
        const rank = 8 - parseInt(squareName[1]);
        const currentFen = (this.fenHistory && this.historyIndex < this.fenHistory.length) ? this.fenHistory[this.historyIndex] : this.fen;
        const grid = this.parseFen(currentFen);
        return grid[rank] ? grid[rank][file] : null;
    }

    initEvents() {
        document.querySelectorAll('.promotion-choice').forEach(choice => {
            choice.addEventListener('click', (e) => {
                const piece = e.currentTarget.getAttribute('data-piece');
                if (this.pendingMove) {
                    const uci = `${this.pendingMove.from}${this.pendingMove.to}${piece}`;
                    this.pendingMove = null;
                    document.getElementById('promotion-modal').style.display = 'none';
                    this.submitMove(uci);
                }
            });
        });

        const hintBtn = document.getElementById('btn-request-hint');
        if (hintBtn) {
            hintBtn.addEventListener('click', () => this.requestHint());
        }

        const favoriteBtn = document.getElementById('btn-toggle-favorite');
        if (favoriteBtn && typeof FAVORITE_URL !== 'undefined') {
            favoriteBtn.addEventListener('click', () => this.toggleFavorite(favoriteBtn));
        }

        const ratingWidget = document.getElementById('rating-widget');
        if (ratingWidget && typeof RATE_URL !== 'undefined') {
            const currentValue = parseInt(ratingWidget.dataset.currentValue || '0');
            this.paintStars(currentValue);
            ratingWidget.querySelectorAll('.rating-star').forEach(star => {
                star.addEventListener('click', (e) => {
                    const value = parseInt(e.currentTarget.getAttribute('data-value'));
                    this.submitRating(value);
                });
            });
        }

        // Reset and Abandon buttons for OBJECTIVE puzzles
        const resetBtn = document.getElementById('btn-reset-puzzle');
        if (resetBtn && typeof RESET_URL !== 'undefined') {
            resetBtn.addEventListener('click', () => this.resetPuzzle());
        }

        const abandonBtn = document.getElementById('btn-abandon-puzzle');
        if (abandonBtn && typeof ABANDON_URL !== 'undefined') {
            abandonBtn.addEventListener('click', () => this.abandonPuzzle());
        }
    }

    resetPuzzle() {
        if (!confirm('¿Reiniciar el problema? Se perderá el progreso actual.')) return;
        
        fetch(RESET_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    this.showFeedback(data.error, 'error');
                    return;
                }
                // Reset game state completely
                this.fenHistory = [data.fen];
                this.historyIndex = 0;
                this.fen = data.fen;
                this.plyIndex = 0;
                this.attemptsCount = 0;
                this.hintsUsed = 0;
                this.startTime = Date.now();
                this.selectedSquare = null;
                this.solved = false;
                this.pendingMove = null;
                this.legalMoves = null;
                this.attemptId = null;  // Clear attempt ID so a new one is created
                
                this.renderBoard();
                this.fetchLegalMoves();
                this.showFeedback(data.message || 'Problema reiniciado. ¡Inténtalo de nuevo!', 'success');
                
                // Hide feedback message after 3 seconds
                setTimeout(() => {
                    const feedbackEl = document.getElementById('puzzle-feedback');
                    if (feedbackEl) feedbackEl.style.display = 'none';
                }, 3000);
            })
            .catch(() => this.showFeedback('Error al reiniciar. Inténtalo de nuevo.', 'error'));
    }

    abandonPuzzle() {
        if (!confirm('¿Abandonar el problema? Se contará como no resuelto.')) return;
        
        fetch(ABANDON_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    this.showFeedback(data.error, 'error');
                    return;
                }
                this.solved = true;
                this.showFeedback(data.message || 'Problema abandonado.', 'error');
            })
            .catch(() => this.showFeedback('Error al abandonar. Inténtalo de nuevo.', 'error'));
    }

    paintStars(value) {
        const stars = document.querySelectorAll('#rating-widget .rating-star');
        stars.forEach(star => {
            const starValue = parseInt(star.getAttribute('data-value'));
            star.textContent = starValue <= value ? '★' : '☆';
        });
    }

    toggleFavorite(button) {
        fetch(FAVORITE_URL, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
            .then(res => res.json())
            .then(data => {
                button.dataset.favorited = data.favorited ? 'true' : 'false';
                button.textContent = data.favorited ? '★ En Favoritos' : '☆ Añadir a Favoritos';
            })
            .catch(() => this.showFeedback('No se pudo actualizar favoritos.', 'error'));
    }

    submitRating(value) {
        fetch(RATE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ value })
        })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    this.showFeedback(Array.isArray(data.error) ? data.error.join(' ') : data.error, 'error');
                    return;
                }
                this.paintStars(value);
                this.showFeedback('¡Gracias por tu valoración!', 'success');
            })
            .catch(() => this.showFeedback('No se pudo enviar la valoración.', 'error'));
    }

    submitMove(uci) {
        this.attemptsCount += 1;
        const timeTaken = Math.round((Date.now() - this.startTime) / 1000);

        fetch(SUBMIT_MOVE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                ply_index: this.plyIndex,
                uci_move: uci,
                time_taken_seconds: timeTaken,
                hints_used: this.hintsUsed,
                attempts_count: this.attemptsCount
            })
        })
            .then(async res => {
                if (!res.ok) {
                    let errMsg = `Error del servidor (${res.status})`;
                    try {
                        const errData = await res.json();
                        if (errData && errData.error) errMsg = errData.error;
                    } catch (e) {}
                    throw new Error(errMsg);
                }
                return res.json();
            })
            .then(data => {
                try {
                    this.handleMoveResult(data, uci);
                } catch (err) {
                    console.error('Error handling move result:', err);
                }
            })
            .catch(err => {
                console.error('Submit move error:', err);
                this.showFeedback(err.message || 'Error de conexión. Inténtalo de nuevo.', 'error');
            });
    }

    handleMoveResult(result, uci) {
        // Handle OBJECTIVE puzzle responses
        if (result.type === 'objective_move') {
            if (!result.success) {
                this.showFeedback(result.message || 'Jugada no válida.', 'error');
                if (this.puzzleType === 'OBJECTIVE' && typeof STATE_URL !== 'undefined') {
                    this.fetchObjectiveState();
                } else {
                    this.renderBoard();
                }
                return;
            }

            // Update FEN from server response
            if (result.fen) {
                this.pushFen(result.fen);
            }

            // Update attempt ID and move counter
            if (result.attempt_id) {
                this.attemptId = result.attempt_id;
            }

            if (result.human_moves !== undefined) {
                this.plyIndex = result.human_moves;
                const counter = document.getElementById('move-counter');
                if (counter) {
                    const maxStr = result.max_moves && result.max_moves > 0 ? result.max_moves : '∞';
                    counter.textContent = `Movimientos: ${result.human_moves} / ${maxStr}`;
                }
            }

            if ((result.outcome === 'success' && result.solved === true) || result.solved === true) {
                // Puzzle won - checkmate achieved
                this.solved = true;
                const msg = result.message || '🏆 ¡Jaque Mate! ¡Excelente trabajo, has resuelto el problema!';
                this.showFeedback(msg, 'success');
                this.showVictoryModal(msg);
            } else if (result.outcome === 'failed') {
                // Puzzle lost - defender gave checkmate or other failure
                this.solved = true;
                this.showFeedback(result.message || 'Problema finalizado.', 'error');
            } else {
                // Puzzle still in progress
                this.showFeedback(result.message || 'Jugada aplicada. El defensor ha respondido.', 'success');
            }

            this.renderBoard();
            this.fetchLegalMoves();

            const botMoveUci = result.bot_move_uci || result.computer_counter_move;
            if (botMoveUci && window.ChessUI) {
                ChessUI.animateMovedPiece(this.boardEl, botMoveUci);
                ChessUI.applyLastMove(this.boardEl, botMoveUci);
            }
            return;
        }

        // Handle SEQUENCE puzzle responses
        if (!result.is_correct) {
            this.showFeedback(result.message || 'Movimiento incorrecto.', 'error');
            this.renderBoard();
            return;
        }

        // Update position FEN from authoritative server response
        if (result.fen) {
            this.pushFen(result.fen);
        } else if (result.computer_counter_move) {
            // Fallback for custom servers without FEN in response
            this.applyUciToFen(result.computer_counter_move);
            this.pushFen(this.fen);
        }

        // Apply student's move locally by advancing ply; server is authoritative on correctness.
        this.plyIndex = result.next_ply_index !== undefined ? result.next_ply_index : this.plyIndex + 1;

        if (result.completed) {
            this.solved = true;
            const msg = result.message || '🏆 ¡Problema resuelto! ¡Excelente trabajo!';
            this.showFeedback(msg, 'success');
            this.showVictoryModal(msg);
        } else {
            this.showFeedback(result.message || '¡Jugada correcta!', 'success');
        }

        this.renderBoard();
        this.fetchLegalMoves();

        if (result.computer_counter_move && window.ChessUI) {
            ChessUI.animateMovedPiece(this.boardEl, result.computer_counter_move);
        }
    }

    // Lightweight local FEN update to reflect the computer's reply move without a full board engine.
    applyUciToFen(uci) {
        const grid = this.parseFen(this.fen);
        const fromFile = uci.charCodeAt(0) - 97;
        const fromRank = 8 - parseInt(uci[1]);
        const toFile = uci.charCodeAt(2) - 97;
        const toRank = 8 - parseInt(uci[3]);

        const movingPiece = grid[fromRank][fromFile];
        grid[fromRank][fromFile] = null;
        grid[toRank][toFile] = uci.length === 5 ? (movingPiece === movingPiece.toUpperCase() ? uci[4].toUpperCase() : uci[4]) : movingPiece;

        const rows = grid.map(row => {
            let fenRow = '';
            let emptyCount = 0;
            row.forEach(cell => {
                if (cell === null) {
                    emptyCount += 1;
                } else {
                    if (emptyCount > 0) { fenRow += emptyCount; emptyCount = 0; }
                    fenRow += cell;
                }
            });
            if (emptyCount > 0) fenRow += emptyCount;
            return fenRow;
        });

        const parts = this.fen.split(' ');
        parts[0] = rows.join('/');
        this.fen = parts.join(' ');
    }

    requestHint() {
        const hintIndex = this.hintsUsed;
        fetch(`${HINT_URL}?index=${hintIndex}`)
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    this.showFeedback(data.error, 'error');
                    return;
                }
                this.hintsUsed += 1;
                const hintTextEl = document.getElementById('hint-text');
                if (hintTextEl) hintTextEl.textContent = data.hint_text;
                const hintBox = document.getElementById('hint-box');
                if (hintBox) hintBox.style.display = 'block';
            })
            .catch(() => this.showFeedback('No se pudo obtener la pista.', 'error'));
    }

    showVictoryModal(message) {
        const modal = document.getElementById('victory-modal');
        if (!modal) return;
        const msgEl = document.getElementById('victory-message');
        if (msgEl) msgEl.textContent = message;
        modal.style.display = 'flex';
    }

    showFeedback(message, type) {
        const feedbackEl = document.getElementById('puzzle-feedback');
        if (!feedbackEl) return;
        feedbackEl.textContent = message;
        feedbackEl.style.display = 'block';
        feedbackEl.style.color = type === 'success' ? 'var(--success-color)' : 'var(--danger-color)';
    }
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

document.addEventListener('DOMContentLoaded', () => {
    window.puzzleApp = new PuzzleSolverApp();
});
