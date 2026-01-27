import styles from './Loading.module.css';

interface LoadingProps {
  text?: string;
  progress?: number;
  showProgress?: boolean;
}

export function Loading({ text, progress = 0, showProgress = true }: LoadingProps) {
  return (
    <div className={styles.container}>
      <div className={styles.spinner} />
      {text && <div className={styles.text}>{text}</div>}
      {showProgress && (
        <>
          <div className={styles.progressBar}>
            <div 
              className={styles.progressFill} 
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
            />
          </div>
          <div className={styles.percent}>{Math.round(progress)}%</div>
        </>
      )}
    </div>
  );
}
