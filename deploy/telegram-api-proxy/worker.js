/**
 * Бесплатный прокси Bot API через Cloudflare Worker.
 * ВМ → https://ВАШ_WORKER.workers.dev/bot<token>/<method> → api.telegram.org
 */
export default {
  async fetch(request) {
    const incoming = new URL(request.url);
    if (incoming.pathname === "/" || incoming.pathname === "/health") {
      return new Response("telegram-api-proxy ok", { status: 200 });
    }

    const target = new URL(
      incoming.pathname + incoming.search,
      "https://api.telegram.org"
    );

    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("cf-connecting-ip");
    headers.delete("cf-ipcountry");
    headers.delete("cf-ray");
    headers.delete("cf-visitor");
    headers.delete("x-forwarded-proto");
    headers.delete("x-real-ip");

    const init = {
      method: request.method,
      headers,
      redirect: "follow",
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    return fetch(target, init);
  },
};
