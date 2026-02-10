const sentimentClass = (label) => {
  if (label === "positive") return "pill positive";
  if (label === "negative") return "pill negative";
  return "pill neutral";
};

export default function LiveFeed({ posts }) {
  return (
    <div className="feed">
      <div className="panel-title">
        <h2>Recent Posts Feed</h2>
        <p>Live stream of social posts</p>
      </div>
      {posts.length === 0 ? (
        <div className="empty-state">Waiting for the first post...</div>
      ) : (
        <div className="feed-list">
          {posts.map((post) => (
            <article key={post.post_id} className="feed-item">
              <div className="feed-meta">
                <span>{post.source}</span>
                <span>
                  {post.created_at
                    ? new Date(post.created_at).toLocaleString()
                    : new Date().toLocaleString()}
                </span>
              </div>
              <p>{post.content}</p>
              <div className={sentimentClass(post.sentiment?.label || post.sentiment_label || "neutral")}>
                {post.sentiment?.label || post.sentiment_label || "neutral"}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
