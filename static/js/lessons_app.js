(function () {
    'use strict';

    const boardEl = document.getElementById('chessboard');
    const chaptersEl = document.getElementById('lesson-chapters');
    const choicesEl = document.getElementById('lesson-choices');
    if (!boardEl || !chaptersEl || !choicesEl || !window.ChessUI) return;

    const chapters = JSON.parse(
        document.getElementById('lesson-session-chapters').textContent
    );
    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    const elements = {
        title: document.getElementById('chapter-heading'),
        intro: document.getElementById('lesson-intro'),
        status: document.getElementById('lesson-status'),
        comment: document.getElementById('lesson-comment'),
        moves: document.getElementById('lesson-moves'),
        color: document.getElementById('lesson-color'),
        mode: document.getElementById('lesson-mode'),
        hint: document.getElementById('lesson-hint'),
        branches: document.getElementById('lesson-toggle-branches'),
        reset: document.getElementById('lesson-reset'),
        back: document.getElementById('lesson-back'),
        forward: document.getElementById('lesson-forward'),
        evaluate: document.getElementById('lesson-evaluate'),
        evaluation: document.getElementById('lesson-evaluation'),
        progressLabel: document.getElementById('lesson-progress-label'),
        progressBar: document.getElementById('lesson-progress-bar')
    };

    let activeChapter = chapters.find((item) =>
        item.id === Number(window.LESSON_INITIAL_CHAPTER_ID)
    ) || chapters[0];
    let tree = [];
    let state = null;
    let selectedSquare = null;
    let hintIndex = 0;
    let historyPaths = [];
    let historyIndex = -1;
    let feedback = '';
    let exploreVariants = true;
    let examHasCompleted = false;
    let correctMoves = 0;
    let mistakes = 0;

    function currentColor() {
        return elements.color.value;
    }

    function currentMode() {
        return elements.mode.value;
    }

    function setStatus(message, kind) {
        elements.status.textContent = message;
        elements.status.dataset.kind = kind || '';
    }

    async function post(action, path, extra) {
        const response = await fetch(activeChapter.play_url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfInput.value,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                action,
                path,
                color: currentColor(),
                ...(extra || {})
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'No se pudo actualizar la lección.');
        return data;
    }

    function pathNodes(path) {
        let candidates = tree;
        const result = [];
        for (const uci of path || []) {
            const node = candidates.find((candidate) => candidate.uci === uci);
            if (!node) break;
            result.push(node);
            candidates = node.variations || [];
        }
        return result;
    }

    function recordHistory(nextState, reset) {
        if (reset) {
            historyPaths = [[]];
            historyIndex = 0;
        }
        const path = nextState.path || [];
        const current = historyPaths[historyIndex] || [];
        if (current.join(' ') === path.join(' ')) return;
        historyPaths = historyPaths.slice(0, historyIndex + 1);
        historyPaths.push(path.slice());
        historyIndex = historyPaths.length - 1;
    }

    function updateProgress(progress) {
        if (!progress) return;
        elements.progressLabel.textContent =
            `${progress.completed_chapters} / ${progress.total_chapters} capítulos completados` +
            ` · ${progress.completed_branches} variantes completadas`;
        elements.progressBar.max = Math.max(1, progress.total_chapters);
        elements.progressBar.value = progress.completed_chapters;
    }

    function selectChapter(chapterId) {
        const next = chapters.find((item) => item.id === Number(chapterId));
        if (!next || next.id === activeChapter.id) return;
        activeChapter = next;
        loadChapter(true);
    }

    async function loadChapter(resetCounters) {
        try {
            const response = await fetch(activeChapter.tree_url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            tree = data.tree || [];
            elements.title.textContent = `${chapters.indexOf(activeChapter) + 1}. ${data.title}`;
            elements.intro.textContent = data.intro || '';
            elements.evaluation.textContent = '';
            elements.comment.textContent = '';
            feedback = '';
            hintIndex = 0;
            selectedSquare = null;
            if (resetCounters) {
                correctMoves = 0;
                mistakes = 0;
                examHasCompleted = false;
            }
            chaptersEl.querySelectorAll('[data-chapter-id]').forEach((button) => {
                button.classList.toggle(
                    'btn-primary',
                    Number(button.dataset.chapterId) === activeChapter.id
                );
                button.classList.toggle(
                    'btn-secondary',
                    Number(button.dataset.chapterId) !== activeChapter.id
                );
            });
            const initial = await post('start', []);
            state = initial;
            recordHistory({ path: [] }, true);
            recordHistory(state, false);
            updateProgress(state.lesson_progress);
            setStatus('Juega en el tablero. El rival responderá siguiendo la línea principal.', '');
            render();
        } catch (error) {
            setStatus(error.message, 'error');
        }
    }

    function renderMoves() {
        const nodes = pathNodes(state.path);
        const startingFen = state.start_fen || null;
        const moveNumber = startingFen
            ? Number(startingFen.split(' ')[5]) || 1
            : 1;
        let turn = startingFen && startingFen.split(' ')[1] === 'b' ? 'black' : 'white';
        let number = moveNumber;
        let text = '';
        nodes.forEach((node) => {
            if (turn === 'white') {
                text += `${number}. `;
                turn = 'black';
            } else {
                text += `${number}... `;
                turn = 'white';
                number += 1;
            }
            text += `${node.san} `;
        });
        elements.moves.textContent = text.trim() || 'Posición inicial';
    }

    function renderComment() {
        if (feedback) {
            const explanation = state.current && state.current.comment;
            const showExplanation = currentMode() !== 'exam' && explanation;
            elements.comment.textContent = showExplanation
                ? `${feedback}\n${explanation}`
                : feedback;
            return;
        }
        const comment = state.current && state.current.comment;
        const visible = currentMode() === 'guided' ||
            (currentMode() === 'exam' && state.completed);
        elements.comment.textContent = visible && comment ? comment : '';
    }

    function renderChoices() {
        choicesEl.replaceChildren();
        const branchesAllowed = currentMode() === 'guided' ||
            exploreVariants ||
            (currentMode() === 'exam' && examHasCompleted);
        elements.branches.hidden = currentMode() === 'guided' ||
            (currentMode() === 'exam' && !examHasCompleted);
        elements.branches.textContent = exploreVariants
            ? 'Ocultar ramas'
            : 'Mostrar ramas (revela jugadas)';
        if (!branchesAllowed) {
            const message = document.createElement('p');
            message.className = 'lesson-help';
            message.textContent = 'Completa tu jugada en el tablero. Las ramas se pueden consultar al activar su exploración.';
            choicesEl.appendChild(message);
            return;
        }
        const replyChoices = (state.reply_choices || []).map((item) => ({
            ...item.node,
            explorePath: item.path,
            exploreType: 'Respuesta alternativa'
        }));
        const choices = replyChoices.concat(state.choices || []);
        const hasRequiredMove = (state.choices || []).some((node) => node.required);
        if (!choices.length) {
            const message = document.createElement('p');
            message.className = 'lesson-help';
            message.textContent = state.completed
                ? 'Fin de esta variante. Puedes volver atrás, repetirla o elegir otro capítulo.'
                : 'No hay continuaciones preparadas desde esta posición.';
            choicesEl.appendChild(message);
            return;
        }

        choices.forEach((node) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-secondary lesson-branch';
            const label = node.exploreType || (node.required
                ? 'Jugada obligatoria'
                : hasRequiredMove
                    ? 'Alternativa no aceptada'
                    : node.accepted === false
                        ? 'Explorar (no aceptada)'
                        : node.main
                            ? 'Línea principal'
                            : 'Alternativa aceptable');
            button.textContent = `${node.san} · ${label}`;
            button.addEventListener('click', () =>
                submitMove('explore', node.uci, node.explorePath)
            );
            choicesEl.appendChild(button);
        });
    }

    function renderBoard() {
        if (!state) return;
        boardEl.replaceChildren();
        const grid = ChessUI.parseFenPlacement(state.fen);
        const flipped = currentColor() === 'black';
        const canMove = state.turn === currentColor() &&
            state.legal_moves && state.legal_moves.length > 0;
        boardEl.classList.toggle('lesson-board-disabled', !canMove);

        for (let row = 0; row < 8; row += 1) {
            for (let col = 0; col < 8; col += 1) {
                const rankIndex = flipped ? 7 - row : row;
                const fileIndex = flipped ? 7 - col : col;
                const file = String.fromCharCode(97 + fileIndex);
                const rank = 8 - rankIndex;
                const squareName = `${file}${rank}`;
                const square = document.createElement('div');
                square.dataset.square = squareName;
                square.className = `square ${(rankIndex + fileIndex) % 2 === 0 ? 'light' : 'dark'}`;
                ChessUI.appendCoordinates(square, {
                    col, row, fileChar: file, rankNum: rank
                });

                const piece = grid[rankIndex][fileIndex];
                if (piece) {
                    square.appendChild(ChessUI.createPieceElement(piece, {
                        onDragStart: (event) => {
                            if (!canMove || !pieceBelongsToStudent(piece)) {
                                event.preventDefault();
                                return;
                            }
                            event.dataTransfer.setData('text/plain', squareName);
                            selectedSquare = squareName;
                        }
                    }));
                }
                square.addEventListener('click', () => handleSquare(squareName, piece));
                square.addEventListener('dragover', (event) => event.preventDefault());
                square.addEventListener('drop', (event) => {
                    event.preventDefault();
                    const from = event.dataTransfer.getData('text/plain');
                    if (from) tryMove(from, squareName);
                });
                if (selectedSquare === squareName) square.classList.add('selected');
                boardEl.appendChild(square);
            }
        }

        if (selectedSquare && canMove) {
            const legal = state.legal_moves
                .filter((uci) => uci.slice(0, 2) === selectedSquare)
                .map((uci) => ({ from: uci.slice(0, 2), to: uci.slice(2, 4) }));
            ChessUI.applyLegalHints(boardEl, selectedSquare, legal, grid);
        }
        const last = state.path && state.path[state.path.length - 1];
        if (last) ChessUI.applyLastMove(boardEl, last);
    }

    function pieceBelongsToStudent(piece) {
        return currentColor() === 'white'
            ? piece === piece.toUpperCase()
            : piece === piece.toLowerCase();
    }

    function handleSquare(square, piece) {
        if (!state || state.turn !== currentColor()) return;
        if (selectedSquare) {
            if (selectedSquare === square) {
                selectedSquare = null;
                renderBoard();
                return;
            }
            const moveFound = tryMove(selectedSquare, square);
            if (moveFound) return;
        }
        if (piece && pieceBelongsToStudent(piece)) {
            selectedSquare = square;
            renderBoard();
        } else {
            selectedSquare = null;
            renderBoard();
        }
    }

    function tryMove(from, to) {
        const candidates = (state.legal_moves || []).filter(
            (uci) => uci.slice(0, 2) === from && uci.slice(2, 4) === to
        );
        if (!candidates.length) return false;
        const uci = candidates.find((move) => move.endsWith('q')) ||
            candidates.find((move) => move.length === 4) || candidates[0];
        selectedSquare = null;
        submitMove('move', uci);
        return true;
    }

    async function submitMove(action, uci, pathOverride) {
        try {
            const response = await post(
                action,
                pathOverride || state.path || [],
                { uci }
            );
            if (response.accepted === false) {
                if (!response.unmodeled) mistakes += 1;
                feedback = response.message;
                setStatus(response.message, response.unmodeled ? 'info' : 'error');
                updateProgress(response.lesson_progress);
                render();
                return;
            }
            state = response;
            hintIndex = 0;
            recordHistory(state, false);
            feedback = action === 'move'
                ? '¡Correcto! Tu jugada forma parte de una línea aceptada.'
                : 'Variante explorada.';
            if (action === 'move') correctMoves += 1;
            if (state.completed) {
                examHasCompleted = true;
                const score = correctMoves + mistakes
                    ? Math.round((correctMoves / (correctMoves + mistakes)) * 100)
                    : 100;
                setStatus(
                    currentMode() === 'exam'
                        ? `Variante completada. Resultado de esta sesión: ${score}%.`
                        : 'Variante completada. Puedes repetirla o explorar otra línea.',
                    'success'
                );
            } else {
                setStatus(feedback, 'success');
            }
            updateProgress(state.lesson_progress);
            render();
            if (response.played && response.played.length) {
                const lastMove = response.played[response.played.length - 1].uci;
                requestAnimationFrame(() =>
                    ChessUI.animateMovedPiece(boardEl, lastMove)
                );
            }
        } catch (error) {
            setStatus(error.message, 'error');
        }
    }

    async function navigate(path) {
        try {
            state = await post('navigate', path);
            historyIndex = historyPaths.findIndex((item) =>
                item.join(' ') === state.path.join(' ')
            );
            selectedSquare = null;
            hintIndex = 0;
            feedback = '';
            render();
        } catch (error) {
            setStatus(error.message, 'error');
        }
    }

    function render() {
        if (!state) return;
        renderBoard();
        renderMoves();
        renderComment();
        renderChoices();
        updateProgress(state.lesson_progress);
        elements.back.disabled = historyIndex <= 0;
        elements.forward.disabled = historyIndex >= historyPaths.length - 1;
        elements.hint.hidden = currentMode() === 'exam';
    }

    async function showHint() {
        const choices = state && state.choices || [];
        if (!choices.length) {
            setStatus('No hay pistas disponibles en esta posición.', 'info');
            return;
        }
        const choice = choices.find((node) => node.main) || choices[0];
        const hints = Array.isArray(choice.hints) ? choice.hints : [];
        if (hintIndex < hints.length) {
            elements.comment.textContent = hints[hintIndex];
            hintIndex += 1;
            return;
        }
        if (hintIndex === 0 && choice.hint) {
            elements.comment.textContent = choice.hint;
            hintIndex += 1;
            return;
        }
        setStatus('No hay más pistas preparadas para esta jugada.', 'info');
    }

    async function evaluatePosition() {
        if (!state) return;
        elements.evaluation.textContent = 'Evaluando posición…';
        try {
            const url = new URL(window.LESSON_EVAL_URL, window.location.origin);
            url.searchParams.set('fen', state.fen);
            url.searchParams.set('mode', 'TRAINING');
            const response = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'No se pudo evaluar la posición.');
            const score = result.mate_in !== null
                ? `Mate en ${result.mate_in}`
                : `${((result.score_cp || 0) / 100).toFixed(2)} peones para el bando al turno`;
            elements.evaluation.textContent = `Evaluación: ${score} · ${result.engine_name}`;
        } catch (error) {
            elements.evaluation.textContent = error.message;
        }
    }

    chaptersEl.addEventListener('click', (event) => {
        const button = event.target.closest('[data-chapter-id]');
        if (button) selectChapter(button.dataset.chapterId);
    });
    document.querySelectorAll('.lesson-chapter-navigation [data-chapter-id]').forEach((button) => {
        button.addEventListener('click', () => selectChapter(button.dataset.chapterId));
    });
    elements.color.addEventListener('change', () => loadChapter(false));
    elements.mode.addEventListener('change', () => {
        exploreVariants = currentMode() === 'guided';
        render();
    });
    elements.branches.addEventListener('click', () => {
        exploreVariants = !exploreVariants;
        render();
    });
    elements.reset.addEventListener('click', () => loadChapter(false));
    elements.hint.addEventListener('click', showHint);
    elements.evaluate.addEventListener('click', evaluatePosition);
    elements.back.addEventListener('click', () => {
        if (historyIndex <= 0) return;
        historyIndex -= 1;
        navigate(historyPaths[historyIndex]);
    });
    elements.forward.addEventListener('click', () => {
        if (historyIndex >= historyPaths.length - 1) return;
        historyIndex += 1;
        navigate(historyPaths[historyIndex]);
    });

    loadChapter(false);
})();
