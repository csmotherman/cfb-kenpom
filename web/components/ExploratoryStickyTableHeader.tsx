"use client";

import { useEffect } from "react";

/** Mirrors the Exploratory table header into a viewport-fixed header while
 * the page scrolls, while keeping horizontal scroll synchronized with the
 * real table. Desktop only; mobile keeps its existing table behavior. */
export default function ExploratoryStickyTableHeader() {
  useEffect(() => {
    let teardown: (() => void) | undefined;
    let stopped = false;

    const install = () => {
      if (stopped || teardown) return;

      const root = document.querySelector<HTMLElement>("#exploratoryTable");
      const scroller = root?.querySelector<HTMLElement>(".table-scroll");
      const table = scroller?.querySelector<HTMLTableElement>(".exploratory-table");
      const thead = table?.tHead;
      if (!root || !scroller || !table || !thead) return;

      const floating = document.createElement("div");
      floating.className = "exploratory-floating-head";
      floating.setAttribute("aria-hidden", "true");

      const floatingScroller = document.createElement("div");
      floatingScroller.className = "exploratory-floating-head__scroll";

      const floatingTable = document.createElement("table");
      floatingTable.className = `${table.className} exploratory-floating-head__table`;

      floatingScroller.appendChild(floatingTable);
      floating.appendChild(floatingScroller);
      root.appendChild(floating);

      const refreshHeader = () => {
        const currentHead = table.tHead;
        if (!currentHead) return;

        floatingTable.querySelector("thead")?.remove();
        const clone = currentHead.cloneNode(true) as HTMLTableSectionElement;
        clone.querySelectorAll<HTMLElement>("[id]").forEach((node) => node.removeAttribute("id"));
        clone.querySelectorAll<HTMLElement>("button, a, [tabindex]").forEach((node) => node.setAttribute("tabindex", "-1"));
        floatingTable.appendChild(clone);
      };

      const syncGeometry = () => {
        const currentHead = table.tHead;
        const cloneHead = floatingTable.tHead;
        if (!currentHead || !cloneHead) return;

        const scrollerRect = scroller.getBoundingClientRect();
        const tableWidth = table.getBoundingClientRect().width;
        floating.style.left = `${scrollerRect.left}px`;
        floating.style.width = `${scrollerRect.width}px`;
        floatingTable.style.width = `${tableWidth}px`;
        floatingTable.style.minWidth = `${tableWidth}px`;

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
        if (!window.matchMedia("(min-width: 769px)").matches) {
          floating.classList.remove("is-visible");
          return;
        }
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
      const onWindowChange = () => updateVisibility();
      const onFloatingClick = (event: MouseEvent) => {
        const target = event.target as HTMLElement | null;
        const cloneButton = target?.closest<HTMLButtonElement>("button.column-sort");
        if (!cloneButton) return;
        const cloneButtons = Array.from(floatingTable.querySelectorAll<HTMLButtonElement>("button.column-sort"));
        const index = cloneButtons.indexOf(cloneButton);
        table.tHead?.querySelectorAll<HTMLButtonElement>("button.column-sort")[index]?.click();
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
      observer.observe(table, { attributes: true, childList: true, subtree: true, attributeFilter: ["class", "aria-sort"] });

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
