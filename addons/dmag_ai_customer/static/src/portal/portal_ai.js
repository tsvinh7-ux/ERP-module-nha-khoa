/* DMAG – AI-17 trợ lý trên cổng bệnh nhân (JS thuần, không phụ thuộc framework). */
(function () {
    "use strict";

    function rpc(url, params) {
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params || {} }),
        })
            .then((r) => r.json())
            .then((r) => {
                if (r.error) {
                    throw new Error((r.error.data && r.error.data.message) || r.error.message);
                }
                return r.result;
            });
    }

    function money(v) {
        return Math.round(v || 0).toLocaleString("vi-VN") + " đ";
    }

    function init(root) {
        const fab = root.querySelector(".dmag-ai-fab");
        const panel = root.querySelector(".dmag-ai-panel");
        const log = root.querySelector(".dmag-ai-log");
        const form = root.querySelector(".dmag-ai-form");
        const input = form.querySelector("input");
        const consentBox = root.querySelector(".dmag-ai-consent");
        const history = [];
        let pending = null;

        function add(role, text, meta) {
            const div = document.createElement("div");
            div.className = "dmag-ai-msg " + (role === "user" ? "is-user" : "is-bot");
            div.textContent = text;
            if (meta) {
                const m = document.createElement("div");
                m.className = "dmag-ai-meta";
                m.textContent = meta;
                div.appendChild(m);
            }
            log.appendChild(div);
            log.scrollTop = log.scrollHeight;
            return div;
        }

        function ask(question) {
            if (!question) {
                return;
            }
            add("user", question);
            const typing = add("bot", "Đang tra hồ sơ của bạn…");
            typing.classList.add("is-typing");
            rpc("/my/dental/assistant/ask", { question, history: history.slice(-8) })
                .then((res) => {
                    typing.remove();
                    if (res.need_consent) {
                        pending = question;
                        consentBox.hidden = false;
                        add("bot", "Bạn cần đồng ý xử lý dữ liệu bằng AI trước khi mình đọc hồ sơ (xem bên dưới).");
                        return;
                    }
                    const meta = res.simulated === undefined ? "" :
                        (res.simulated ? "Giả lập" : "Claude") + (res.estimated_cost_vnd ? " · ~" + money(res.estimated_cost_vnd) : "");
                    add("bot", res.answer || "…", meta);
                    history.push({ role: "user", content: question });
                    history.push({ role: "assistant", content: res.answer || "" });
                })
                .catch((err) => {
                    typing.remove();
                    add("bot", "Xin lỗi, trợ lý đang gặp lỗi: " + err.message);
                });
        }

        fab.addEventListener("click", () => {
            panel.hidden = !panel.hidden;
            root.classList.toggle("is-open", !panel.hidden);
            if (!panel.hidden) {
                input.focus();
            }
        });
        root.querySelector(".dmag-ai-close").addEventListener("click", () => {
            panel.hidden = true;
            root.classList.remove("is-open");
        });
        root.querySelectorAll(".dmag-ai-quick button").forEach((b) =>
            b.addEventListener("click", () => ask(b.dataset.q))
        );
        root.querySelector(".dmag-ai-agree").addEventListener("click", () => {
            rpc("/my/dental/assistant/consent", {}).then(() => {
                consentBox.hidden = true;
                if (pending) {
                    const q = pending;
                    pending = null;
                    log.lastChild && log.lastChild.remove();
                    log.lastChild && log.lastChild.remove();
                    ask(q);
                }
            });
        });
        form.addEventListener("submit", (ev) => {
            ev.preventDefault();
            const q = input.value.trim();
            input.value = "";
            ask(q);
        });
        if (window.location.hash === "#ai") {
            fab.click();
        }
    }

    function boot() {
        const root = document.getElementById("dmag_ai_assistant");
        if (root && !root.dataset.ready) {
            root.dataset.ready = "1";
            init(root);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
