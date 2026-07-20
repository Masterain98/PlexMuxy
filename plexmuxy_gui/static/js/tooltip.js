/* Cursor-following tooltip.
 *
 * Replaces the old CSS `::after` tooltip, which was pinned to the horizontal
 * centre of the hovered element (so it could sit far from the pointer and run
 * off-screen near a window edge). This implementation:
 *   - shows the tooltip next to the pointer on hover/move,
 *   - anchors it just below the element for keyboard focus, and
 *   - clamps the position so it never leaves the viewport.
 *
 * A single shared element (`#cursor-tooltip`) is reused for every target; the
 * text comes from each element's `data-tooltip` attribute (set both in markup
 * and dynamically by other scripts, e.g. the window controls).
 */
(function () {
  const tooltip = document.getElementById("cursor-tooltip");
  if (!tooltip) return;

  let activeTarget = null;

  const GAP = 12;       // distance from the pointer / element edge
  const MARGIN = 8;     // minimum distance kept from the viewport edge

  function positionTooltip(preferredLeft, preferredTop) {
    const rect = tooltip.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let left = preferredLeft;
    let top = preferredTop;

    if (left + rect.width > viewportWidth - MARGIN) {
      left = viewportWidth - MARGIN - rect.width;
    }
    if (left < MARGIN) left = MARGIN;

    if (top + rect.height > viewportHeight - MARGIN) {
      top = viewportHeight - MARGIN - rect.height;
    }
    if (top < MARGIN) top = MARGIN;

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function showForElement(element, clientX, clientY) {
    const text = element.dataset.tooltip;
    if (!text) return;
    activeTarget = element;
    tooltip.textContent = text;
    if (typeof clientY === "number") {
      // Pointer hover: place down-right of the cursor, then clamp on-screen.
      positionTooltip(clientX + GAP, clientY + GAP);
    } else {
      // Keyboard focus: anchor just below the element's left edge, then clamp.
      const box = element.getBoundingClientRect();
      positionTooltip(box.left, box.bottom + GAP);
    }
    tooltip.classList.add("is-visible");
  }

  function hide() {
    activeTarget = null;
    tooltip.classList.remove("is-visible");
  }

  document.addEventListener("pointerover", (event) => {
    const element = event.target.closest("[data-tooltip]");
    if (!element || !element.dataset.tooltip) return;
    showForElement(element, event.clientX, event.clientY);
  });

  document.addEventListener("pointermove", (event) => {
    if (!activeTarget) return;
    const element = event.target.closest("[data-tooltip]");
    if (element !== activeTarget) return;
    positionTooltip(event.clientX + GAP, event.clientY + GAP);
  });

  document.addEventListener("pointerout", (event) => {
    const element = event.target.closest("[data-tooltip]");
    if (!element) return;
    // Ignore moves between the element and its own descendants.
    if (event.relatedTarget && element.contains(event.relatedTarget)) return;
    // Moving straight to another tooltip target is handled by its pointerover,
    // so don't hide here (prevents a flicker between adjacent targets).
    if (
      event.relatedTarget &&
      typeof event.relatedTarget.closest === "function" &&
      event.relatedTarget.closest("[data-tooltip]")
    ) {
      return;
    }
    hide();
  });

  document.addEventListener("focusin", (event) => {
    const element = event.target.closest("[data-tooltip]");
    if (!element || !element.dataset.tooltip) return;
    showForElement(element);
  });

  document.addEventListener("focusout", (event) => {
    const element = event.target.closest("[data-tooltip]");
    if (!element) return;
    hide();
  });
})();
