import type { Metadata } from "next";

export const metadata: Metadata = { title: "登录 | Operion" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string | string[] }>;
}) {
  const expired = (await searchParams).reason === "session_expired";
  return (
    <main className="login-page" lang="zh-CN">
      <section className="login-card" aria-labelledby="login-title">
        <p className="login-brand">OPERION</p>
        <h1 id="login-title">{expired ? "重新登录 Operion" : "登录 Operion"}</h1>
        {expired ? (
          <div className="login-notice" role="status">
            <p>会话已超时或已失效，请重新登录。</p>
            <p lang="en">Your session has expired or is no longer valid.</p>
          </div>
        ) : (
          <p>登录后继续访问已授权的工作区。</p>
        )}
        <p className="login-help">已保存的对话会保留。登录后可以继续查看历史，并重新发送未完成的问题。</p>
        <form action="/oauth2/start" method="get">
          <input type="hidden" name="rd" value="/" />
          <button className="login-button" type="submit">{expired ? "重新登录" : "登录"}</button>
        </form>
      </section>
    </main>
  );
}
