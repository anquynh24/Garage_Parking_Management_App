/**
 * Makes a table with a header row + a ".filter-row" of <input class="col-filter">
 * sortable (click a header to sort by it) and filterable (type in the filter row).
 * Call once per table: makeSortableFilterable('my-table-id')
 */
function makeSortableFilterable(tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;

  const tbody = table.querySelector('tbody');
  const headers = table.querySelectorAll('thead tr:first-child th');
  const filterInputs = table.querySelectorAll('.col-filter');

  function applyFilters() {
    const filters = Array.from(filterInputs).map(inp => inp.value.trim().toLowerCase());
    Array.from(tbody.rows).forEach(row => {
      const visible = Array.from(row.cells).every((cell, i) => {
        if (!filters[i]) return true;
        return cell.textContent.toLowerCase().includes(filters[i]);
      });
      row.style.display = visible ? '' : 'none';
    });
  }

  filterInputs.forEach(inp => inp.addEventListener('input', applyFilters));

  let sortState = { columnIndex: null, ascending: true };

  function sortByColumn(columnIndex, type) {
    const rows = Array.from(tbody.rows);
    const ascending = sortState.columnIndex === columnIndex ? !sortState.ascending : true;

    rows.sort((a, b) => {
      let valA = a.cells[columnIndex].textContent.trim();
      let valB = b.cells[columnIndex].textContent.trim();
      if (type === 'num') {
        valA = parseFloat(valA) || 0;
        valB = parseFloat(valB) || 0;
        return ascending ? valA - valB : valB - valA;
      }
      return ascending ? valA.localeCompare(valB) : valB.localeCompare(valA);
    });

    rows.forEach(row => tbody.appendChild(row));
    sortState = { columnIndex, ascending };

    headers.forEach((h, i) => {
      const arrow = h.querySelector('.sort-arrow');
      if (arrow) arrow.textContent = i === columnIndex ? (ascending ? ' ▲' : ' ▼') : '';
    });
  }

  headers.forEach((th, index) => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => sortByColumn(index, th.dataset.type || 'text'));
  });
}
