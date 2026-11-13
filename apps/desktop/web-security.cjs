const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; frame-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'";
async function listenLoopback(server, preferred = 0) {
  function listen(port) {
    return new Promise((resolve, reject) => {
      const failed = (error) => {
        server.removeListener("listening", ready);
        reject(error);
      };
      const ready = () => {
        server.removeListener("error", failed);
        resolve();
      };
      server.once("error", failed);
      server.once("listening", ready);
      server.listen(port, "127.0.0.1");
    });
  }
  try {
    await listen(preferred);
  } catch (error) {
    if (error.code !== "EADDRINUSE" || !preferred) throw error;
    await listen(0);
  }
  return server.address().port;
}
module.exports = { CSP, listenLoopback };
