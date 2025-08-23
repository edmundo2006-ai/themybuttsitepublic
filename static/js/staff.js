let renderedOrderIds = new Set();
let maxSeenId = 0; // newest ID we've seen

// --- Helpers ---
function seedFromSSR() {
  const ids = [...document.querySelectorAll('#orders-table-body tr[id^="order-"]')]
    .map(tr => parseInt(tr.id.replace('order-', ''), 10))
    .filter(Number.isInteger);

  ids.forEach(id => renderedOrderIds.add(id));
  if (ids.length) maxSeenId = Math.max(...ids);
}

function buildOrderRow(order) {
  const row = document.createElement("tr");
  row.id = `order-${order.id}`; 
  row.className = "bg-white hover:bg-primary/5 transition dark:bg-gray-900 dark:hover:bg-primary/10";

  const itemsHtml = `
    <ul class="space-y-3">
      ${order.items.map(item => `
        <li class="rounded-lg bg-white ring-1 ring-gray-200 p-3 dark:bg-gray-900 dark:ring-gray-700">
          <div class="flex items-baseline gap-2">
            <strong class="text-gray-900 dark:text-gray-100">${item.menu_item_name}</strong>
            <span class="text-gray-500 dark:text-gray-400">${formatPrice(item.menu_item_price)}</span>
          </div>

          ${item.selected_ingredients && item.selected_ingredients.length ? `
          <div class="mt-2 text-xs text-gray-600 dark:text-gray-300">
            <div class="font-semibold text-gray-700 dark:text-gray-200">Ingredients:</div>
            <ul class="mt-1 list-disc pl-5 space-y-0.5">
              ${item.selected_ingredients.map(ing => `
                <li>
                  ${ing.ingredient_name}
                  ${Number(ing.add_price) > 0 ? `<span class="text-gray-500 dark:text-gray-400">(+${formatPrice(ing.add_price)})</span>` : ""}
                </li>
              `).join("")}
            </ul>
          </div>
          ` : ""}
        </li>
      `).join("")}

      ${order.specifications ? `
      <li class="rounded-lg bg-primary/5 ring-1 ring-primary/10 p-3 dark:bg-primary/10 dark:ring-primary/20">
        <p class="text-sm text-gray-700 dark:text-gray-200">
          <strong class="text-primary">Specifications:</strong> ${order.specifications}
        </p>
      </li>
      ` : ""}
    </ul>
  `;

  row.innerHTML = `
    <td class="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">${order.id}</td>
    <td class="px-4 py-3 text-gray-800 dark:text-gray-200">${order.name}</td>
    <td class="px-4 py-3 text-gray-900 dark:text-gray-100">${formatPrice(order.total_price)}</td>

    <td class="px-4 py-3 align-top">
      <form method="POST" action="${window.URLS.updateOrder}" class="space-y-2">
        <input type="hidden" name="order_id" value="${order.id}">
        <select name="status" class="form-control">
          <option value="pending" ${order.status === "pending" ? "selected" : ""}>Pending</option>
          <option value="done" ${order.status === "done" ? "selected" : ""}>Done</option>
        </select>
        <button type="submit" class="btn btn-sm btn-primary">Update</button>
      </form>
    </td>

    <td class="px-4 py-3 align-top">
      <form method="POST" action="${window.URLS.updatePayment}" class="space-y-2">
        <input type="hidden" name="order_id" value="${order.id}">
        <select name="status" class="form-control">
          <option value="1" ${order.paid ? "selected" : ""}>Yes</option>
          <option value="0" ${!order.paid ? "selected" : ""}>No</option>
        </select>
        <button type="submit" class="btn btn-sm btn-primary">Update</button>
      </form>
    </td>
    
    <td class="px-4 py-3 text-gray-700 dark:text-gray-300">${order.timestamp}</td>

    <td class="px-4 py-3">
      ${itemsHtml}
    </td>
  `;
  return row;
}


// --- Fetch NEW orders only via POST ---
async function fetchNewOrdersPost() {
  try {
    const res = await fetch(window.URLS.ordersJson, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ since_id: maxSeenId })
    });

    const data = await res.json();
    const orders = data?.orders || [];
    const max_id = typeof data?.max_id === "number" ? data.max_id : maxSeenId;

    const tbody = document.getElementById("orders-table-body");
    if (!tbody) return;

    orders.forEach(order => {
      // 🚫 if row already exists in DOM, skip
      if (document.getElementById(`order-${order.id}`)) return;

      if (!renderedOrderIds.has(order.id)) {
        const row = buildOrderRow(order);
        tbody.prepend(row);
        renderedOrderIds.add(order.id);
      }
    });

    if (max_id > maxSeenId) maxSeenId = max_id;
  } catch (err) {
    console.error("Error fetching new orders:", err);
  }
}

// --- Socket.IO: ONLY fetch on server events ---
const socket = io("/staff");

// seed from SSR and join on connect (no network calls until server emits)

socket.on("connect", () => {
  seedFromSSR();
  socket.emit("join_staff"); // no args
});

socket.on("order_update", (data) => {
  console.log("🔁 Order update received:", data);
  fetchNewOrdersPost();
});

function formatPrice(cents) {
  if (cents == null || isNaN(cents)) return "";
  if (cents % 100 === 0) {
    return `$${cents / 100}`;       // whole dollars
  }
  return `$${(cents / 100).toFixed(2)}`;
}
