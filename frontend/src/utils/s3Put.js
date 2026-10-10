/**
 * `PUT` de um ficheiro para um URL pré-assinado do S3 (com progresso).
 *
 * Fica num módulo próprio porque é a ÚNICA parte do envio que fala com o
 * mundo fora da nossa API — e por isso a que os testes substituem: um XHR
 * a sério não existe no jsdom, e o resto do fluxo (pedir o URL, confirmar)
 * é o que interessa provar.
 *
 * O `Content-Type` TEM de ser o mesmo com que o servidor assinou o URL.
 */
export function putParaS3(uploadUrl, file, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error("Erro ao enviar o ficheiro."));
    xhr.onerror = () => reject(new Error("Erro de ligação ao enviar o ficheiro."));
    xhr.send(file);
  });
}
