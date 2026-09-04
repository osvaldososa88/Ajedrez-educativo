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
        this.sideToMove = PUZZLE_SIDE_TO_MOVE; // 'white' or 'black'
        this.plyIndex = 0;
        this.attemptsCount = 0;
        this.hintsUsed = 0;
        this.startTime = Date.now();
        this.selectedSquare = null;
        this.solved = false;
        this.pendingMove = null;

        this.renderBoard();
        this.initEvents();
        if (window.ChessUI) {
            ChessUI.paintPromotionChoices(
                document.getElementById('promotion-modal'),
                this.sideToMove === 'black' ? 'black' : 'white'
            );
        }
    }

    parseFen(fen) {
        return window.ChessUI ? ChessUI.parseFenPlacement(fen) : [];
    }

    renderBoard() {
        this.boardEl.innerHTML = '';
        if (!window.ChessUI) return;
        const grid = this.parseFen(this.fen);
        const isFlipped = (this.sideToMove === 'black');

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
                            if (!this.solved) {
                                e.dataTransfer.setData('text/plain', squareName);
                                e.dataTransfer.effectAllowed = 'move';
                                this.selectedSquare = squareName;
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

        if (this.selectedSquare) {
            const sqEl = this.boardEl.querySelector(`[data-square="${this.selectedSquare}"]`);
            if (sqEl) sqEl.classList.add('selected');
        }
    }

    handleSquareClick(squareName) {
        if (this.solved) return;

        if (!this.selectedSquare) {
            this.selectedSquare = squareName;
            this.renderBoard();
            return;
        }

        if (this.selectedSquare === squareName) {
            this.selectedSquare = null;
            this.renderBoard();
            return;
        }

        const fromSq = this.selectedSquare;
        this.selectedSquare = null;

        // Detect promotion (pawn reaching last rank)
        const isPromotionRank = squareName.endsWith('8') || squareName.endsWith('1');
        const grid = this.parseFen(this.fen);
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
        const grid = this.parseFen(this.fen);
        return grid[rank][file];
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
            .then(res => res.json())
            .then(data => this.handleMoveResult(data))
            .catch(() => this.showFeedback('Error de conexión. Inténtalo de nuevo.', 'error'));
    }

    handleMoveResult(result) {
        const feedbackEl = document.getElementById('puzzle-feedback');

        if (!result.is_correct) {
            this.showFeedback(result.message || 'Movimiento incorrecto.', 'error');
            this.renderBoard();
            return;
        }

        // Apply student's move locally by advancing ply; server is authoritative on correctness.
        this.plyIndex = result.next_ply_index !== undefined ? result.next_ply_index : this.plyIndex + 1;

        if (result.computer_counter_move) {
            this.applyUciToFen(result.computer_counter_move);
        }

        if (result.completed) {
            this.solved = true;
            this.showFeedback(result.message || '¡Problema resuelto!', 'success');
        } else {
            this.showFeedback(result.message || '¡Jugada correcta!', 'success');
        }

        this.renderBoard();
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
