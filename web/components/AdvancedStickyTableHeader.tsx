"use client";

import { useEffect } from "react";

/**
 * Keeps the Advanced table's existing header visible while the page scrolls.
 *
 * The real table must stay inside an overflow-x container so users can swipe
 * horizontally. That overflow container prevents a normal CSS sticky thead
 * from sticking to the browser viewport, so this component mirrors only the
 * existing thead while it is above the viewport and keeps its horizontal
 * scroll position synchronized with the real table.
 *
 * No table sizing, typography, colors, or row markup are changed here.
 */
export default function AdvancedStickyTableHeader() {
  useEffect(() => {
    let teardown: (() => void) | undefined;
    let stopped = false;

    const install = () => {
      if (stopped || teardown) return;

      const root = document.querySelector<HTMLElement>("#advancedTable");
      const scroller = root?.querySelector<HTMLElement>(".table-scroll");
      const table = scroller?.querySelector<HTMLTableElement>(".adv-table");
      const thead = table?.tHead;

      if (!root || !scroller || !table || !thead) return;

      const floating = document.createElement("div");
      floating.className = "advanced-floating-head";
      floating.setAttribute("aria-hidden", "true");

      const floatingScroller = document.createElement("div");
      floatingScroller.className = "advanced-floating-head__scroll";

      const floatingTable = document.createElement("table");
      floatingTable.className = `${table.className} advanced-floating-head__table`;

      floatingScroller.appendChild(floatingTable);
      floating.appendChild(floatingScroller);
      root.appendChild(floating);

      const copyTableState = () => {
        for (const attr of Array.from(floatingTable.attributes)) {
          if (attr.name.startsWith("data-")) floatingTable.removeAttribute(attr.name);
        }
        for (const attr of Array.from(table.attributes)) {
          if (attr.name.startsWith("data-")) floatingTable.setAttribute(attr.name, attr.value);
        }
      };

      const refreshHeader = () => {
        const currentHead = table.tHead;
        if (!currentHead) return;

        copyTableState();
        floatingTable.querySelector("thead")?.remove();
        const clone = currentHead.cloneNode(true) as HTMLTableSectionElement;

        clone.querySelectorAll<HTMLElement>("[id]").forEach((node) => node.removeAttribute("id"));
        clone.querySelectorAll<HTMLElement>("button, a, [tabindex]").forEach((node) => {
          node.setAttribute("tabindex", "-1");
        });

        floatingTable.appendChild(clone);
      };

      const syncGeometry = () => {
        const currentHead = table.tHead;
        const cloneHead = floatingTable.tHead;
        if (!currentHead || !cloneHead) return;

        const scrollerRect = scroller.getBoundingClientRect();
        floating.style.left = `${scrollerRect.left}px`;
        floating.style.width = `${scrollerRect.width}px`;
        floatingTable.style.width = `${table.getBoundingClientRect().width}px`;
        floatingTable.style.minWidth = `${table.getBoundingClientRect().width}px`;

        const sourceRows = Array.from(currentHead.rows);
        const cloneRows = Array.from(cloneHead.rows);
        sourceRows.forEach((row, rowIndex) => {
          const cloneRow = cloneRows[rowIndex];
          if (!cloneRow) return;

          Array.from(row.cells).forEach((cell, cellIndex) => {
            const cloneCell = cloneRow.cells[cellIndex] as HTMLElement | undefined;
            if (!cloneCell) return;
            const width = cell.getBoundingClientRect().width;
            cloneCell.style.width = `${width}px`;
            cloneCell.style.minWidth = `${width}px`;
            cloneCell.style.maxWidth = `${width}px`;
          });
        });

        floatingScroller.scrollLeft = scroller.scrollLeft;
      };

      const updateVisibility = () => {
        const rect = scroller.getBoundingClientRect();
        const headerHeight = table.tHead?.getBoundingClientRect().height ?? 0;
        const shouldShow = rect.top < 0 && rect.bottom > headerHeight;
        floating.classList.toggle("is-visible", shouldShow);
        if (shouldShow) syncGeometry();
      };

      refreshHeader();
      syncGeometry();
      updateVisibility();

      const onTableScroll = () => {
        floatingScroller.scrollLeft = scroller.scrollLeft;
      };

      const onWindowChange = () => {
        updateVisibility();
      };

      const onFloatingClick = (event: MouseEvent) => {
        const target = event.target as HTMLElement | null;
        const cloneButton = target?.closest<HTMLButtonElement>("button.column-sort");
        if (!cloneButton) return;

        const cloneButtons = Array.from(floatingTable.querySelectorAll<HTMLButtonElement>("button.column-sort"));
        const index = cloneButtons.indexOf(cloneButton);
        const sourceButton = table.tHead?.querySelectorAll<HTMLButtonElement>("button.column-sort")[index];
        sourceButton?.click();
      };

      let refreshFrame = 0;
      const observer = new MutationObserver(() => {
        cancelAnimationFrame(refreshFrame);
        refreshFrame = requestAnimationFrame(() => {
          refreshHeader();
          syncGeometry();
          updateVisibility();
        });
      });

      observer.observe(table, {
        attributes: true,
        childList: true,
        subtree: true,
        attributeFilter: ["data-view", "data-perspective", "aria-sort"],
      });

      const resizeObserver = new ResizeObserver(() => {
        syncGeometry();
        updateVisibility();
      });
      resizeObserver.observe(scroller);
      resizeObserver.observe(table);

      scroller.addEventListener("scroll", onTableScroll, { passive: true });
      window.addEventListener("scroll", onWindowChange, { passive: true });
      window.addEventListener("resize", onWindowChange, { passive: true });
      floating.addEventListener("click", onFloatingClick);

      teardown = () => {
        cancelAnimationFrame(refreshFrame);
        observer.disconnect();
        resizeObserver.disconnect();
        scroller.removeEventListener("scroll", onTableScroll);
        window.removeEventListener("scroll", onWindowChange);
        window.removeEventListener("resize", onWindowChange);
        floating.removeEventListener("click", onFloatingClick);
        floating.remove();
      };
    };

    install();
    const bodyObserver = new MutationObserver(install);
    bodyObserver.observe(document.body, { childList: true, subtree: true });

    return () => {
      stopped = true;
      bodyObserver.disconnect();
      teardown?.();
    };
  }, []);

  return null;
}
