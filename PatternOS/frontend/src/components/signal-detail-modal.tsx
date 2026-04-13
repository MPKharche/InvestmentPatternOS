"use client";
import { useState, useRef, useEffect } from "react";
import { X, ExternalLink, TrendingUp, TrendingDown, Volume2, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import styles from "./signal-detail-modal.module.css";

interface SignalDetailModalProps {
  signal: {
    symbol: string;
    confidence_score: number;
    base_score: number;
    timeframe: string;
    analysis: string;
    key_levels: {
      entry: number;
      support: number;
      resistance: number;
      stop_loss: number;
    };
    rule_snapshot?: Record<string, any>;
  };
  onClose: () => void;
  onOpenChart?: (symbol: string) => void;
}

export function SignalDetailModal({ signal, onClose, onOpenChart }: SignalDetailModalProps) {
  const [activeTab, setActiveTab] = useState<"chart" | "analysis">("chart");
  const chartRef = useRef<HTMLDivElement>(null);

  // Calculate risk/reward metrics
  const entry = signal.key_levels.entry;
  const support = signal.key_levels.support;
  const resistance = signal.key_levels.resistance;
  const stopLoss = signal.key_levels.stop_loss;

  // L1 and L2 targets (1.618 and 2.618 Fibonacci extensions)
  const moveRange = entry - stopLoss;
  const l1Target = entry + moveRange * 1.618;
  const l2Target = entry + moveRange * 2.618;

  // Loss risk levels
  const l1LossRisk = entry - support;
  const l2LossRisk = entry - stopLoss;

  // Profit potential percentages
  const l1ProfitPct = ((l1Target - entry) / entry * 100).toFixed(2);
  const l2ProfitPct = ((l2Target - entry) / entry * 100).toFixed(2);
  const l1RiskPct = (-(l1LossRisk / entry) * 100).toFixed(2);
  const l2RiskPct = (-(l2LossRisk / entry) * 100).toFixed(2);

  // Risk/Reward Ratio
  const riskRewardL1 = (Math.abs(parseFloat(l1ProfitPct)) / Math.abs(parseFloat(l1RiskPct))).toFixed(2);
  const riskRewardL2 = (Math.abs(parseFloat(l2ProfitPct)) / Math.abs(parseFloat(l2RiskPct))).toFixed(2);

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h2 className={styles.title}>{signal.symbol}</h2>
            <Badge variant="outline" className={styles.timeframe}>{signal.timeframe}</Badge>
            <Badge className={styles.confidenceBadge}>
              {signal.confidence_score.toFixed(1)}%
            </Badge>
          </div>
          <div className={styles.headerRight}>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => onOpenChart?.(signal.symbol)}
              title="Open chart in new tab"
              className={styles.externalLink}
            >
              <ExternalLink className="w-4 h-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={onClose}
              className={styles.closeButton}
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        <div className={styles.container}>
          {/* Main Chart Section (75% width) */}
          <div className={styles.chartSection}>
            <div className={styles.chartTabs}>
              <button
                className={`${styles.tab} ${activeTab === "chart" ? styles.active : ""}`}
                onClick={() => setActiveTab("chart")}
              >
                <Activity className="w-4 h-4" />
                Chart & Indicators
              </button>
              <button
                className={`${styles.tab} ${activeTab === "analysis" ? styles.active : ""}`}
                onClick={() => setActiveTab("analysis")}
              >
                <TrendingUp className="w-4 h-4" />
                Detailed Analysis
              </button>
            </div>

            {activeTab === "chart" && (
              <div className={styles.chartContainer}>
                <div ref={chartRef} className={styles.chartFrame}>
                  {/* Placeholder for TradingView chart */}
                  <div className={styles.chartPlaceholder}>
                    <div className={styles.chartHeader}>
                      <h3>{signal.symbol} - Daily Chart</h3>
                      <div className={styles.indicators}>
                        <span className={styles.indicator}>RSI</span>
                        <span className={styles.indicator}>MACD</span>
                        <span className={styles.indicator}>Bollinger Bands</span>
                        <span className={styles.indicator}>Volume</span>
                      </div>
                    </div>
                    <div className={styles.chartImage}>
                      [Chart with indicators would be rendered here]
                    </div>
                  </div>
                </div>

                {/* Key Levels Overlay */}
                <div className={styles.keyLevels}>
                  <div className={styles.levelItem}>
                    <span className={styles.levelLabel}>Resistance</span>
                    <span className={styles.levelValue}>{resistance.toFixed(2)}</span>
                  </div>
                  <div className={styles.levelItem}>
                    <span className={styles.levelLabel}>Entry</span>
                    <span className={styles.levelValue} style={{ color: "#3b82f6" }}>
                      {entry.toFixed(2)}
                    </span>
                  </div>
                  <div className={styles.levelItem}>
                    <span className={styles.levelLabel}>Support</span>
                    <span className={styles.levelValue}>{support.toFixed(2)}</span>
                  </div>
                  <div className={styles.levelItem}>
                    <span className={styles.levelLabel}>Stop Loss</span>
                    <span className={styles.levelValue} style={{ color: "#ef4444" }}>
                      {stopLoss.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "analysis" && (
              <div className={styles.analysisContent}>
                {/* LLM Analysis Text */}
                <div className={styles.analysisSection}>
                  <h4>Signal Analysis</h4>
                  <p>{signal.analysis || "No analysis available"}</p>
                </div>

                {/* Rule Breakdown */}
                {signal.rule_snapshot && (
                  <div className={styles.rulesSection}>
                    <h4>Rule Evaluation</h4>
                    <div className={styles.rulesList}>
                      {Object.entries(signal.rule_snapshot).map(([key, value]: [string, any]) => (
                        <div key={key} className={styles.ruleItem}>
                          <span className={styles.ruleName}>{key}</span>
                          <span className={styles.ruleStatus}>
                            {value.passed ? "✓" : "✗"} {value.detail}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Sidebar (25% width) */}
          <div className={styles.sidebar}>
            {/* Risk/Reward Table */}
            <div className={styles.metricsCard}>
              <h4 className={styles.cardTitle}>Risk/Reward Analysis</h4>
              <table className={styles.metricsTable}>
                <thead>
                  <tr>
                    <th>Level</th>
                    <th>Target</th>
                    <th>Profit</th>
                    <th>R:R</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className={styles.l1Row}>
                    <td>L1</td>
                    <td>{l1Target.toFixed(2)}</td>
                    <td className={styles.positive}>+{l1ProfitPct}%</td>
                    <td>{riskRewardL1}</td>
                  </tr>
                  <tr className={styles.l2Row}>
                    <td>L2</td>
                    <td>{l2Target.toFixed(2)}</td>
                    <td className={styles.positive}>+{l2ProfitPct}%</td>
                    <td>{riskRewardL2}</td>
                  </tr>
                  <tr className={styles.stopRow}>
                    <td colspan="4" style={{ paddingTop: "8px", borderTop: "1px solid #333" }}>
                      <div className={styles.riskRow}>
                        <span>Loss Risk L1</span>
                        <span className={styles.negative}>-{l1RiskPct}%</span>
                      </div>
                      <div className={styles.riskRow}>
                        <span>Loss Risk L2</span>
                        <span className={styles.negative}>-{l2RiskPct}%</span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Evaluation Sections */}

            {/* 1. Price & Volume */}
            <div className={styles.evalCard}>
              <h4 className={styles.evalTitle}>
                <TrendingUp className="w-4 h-4" /> Price & Volume
              </h4>
              <div className={styles.evalContent}>
                <div className={styles.evalItem}>
                  <span>Volume Confirmation</span>
                  <Badge variant="outline" className={styles.positiveBadge}>Strong</Badge>
                </div>
                <div className={styles.evalItem}>
                  <span>Price Action</span>
                  <Badge variant="outline" className={styles.positiveBadge}>Bullish</Badge>
                </div>
                <div className={styles.evalItem}>
                  <span>Breakout Quality</span>
                  <Badge variant="outline" className={styles.positiveBadge}>Confirmed</Badge>
                </div>
                <p className={styles.evalDesc}>
                  Strong volume spike (17.7x avg) confirms breakout conviction. Sustained above key resistance.
                </p>
              </div>
            </div>

            {/* 2. Indicators & Technical */}
            <div className={styles.evalCard}>
              <h4 className={styles.evalTitle}>
                <Activity className="w-4 h-4" /> Indicators & Technical
              </h4>
              <div className={styles.evalContent}>
                <div className={styles.evalItem}>
                  <span>RSI</span>
                  <span className={styles.value}>65/100</span>
                </div>
                <div className={styles.evalItem}>
                  <span>MACD</span>
                  <span className={styles.value}>Positive</span>
                </div>
                <div className={styles.evalItem}>
                  <span>EMA Stack</span>
                  <span className={styles.value}>Bullish</span>
                </div>
                <div className={styles.evalItem}>
                  <span>Trend Strength</span>
                  <Badge variant="outline" className={styles.positiveBadge}>Strong</Badge>
                </div>
              </div>
            </div>

            {/* 3. Sector & Economy */}
            <div className={styles.evalCard}>
              <h4 className={styles.evalTitle}>
                <Volume2 className="w-4 h-4" /> Sector & Economy
              </h4>
              <div className={styles.evalContent}>
                <div className={styles.evalItem}>
                  <span>Sector Momentum</span>
                  <Badge variant="outline" className={styles.neutralBadge}>Neutral</Badge>
                </div>
                <div className={styles.evalItem}>
                  <span>Market Condition</span>
                  <Badge variant="outline" className={styles.neutralBadge}>Mixed</Badge>
                </div>
                <div className={styles.evalItem}>
                  <span>Macro Risk</span>
                  <Badge variant="outline" className={styles.cautionBadge}>Moderate</Badge>
                </div>
                <p className={styles.evalDesc}>
                  Retail sector sensitivity to macro headwinds warrants moderate caution. Monitor broader indices.
                </p>
              </div>
            </div>

            {/* Score Breakdown */}
            <div className={styles.scoreCard}>
              <h4>Confidence Breakdown</h4>
              <div className={styles.scoreBar}>
                <div className={styles.scoreLabel}>Rule Match</div>
                <div className={styles.bar}>
                  <div className={styles.fill} style={{ width: `${signal.base_score}%` }} />
                </div>
                <span>{signal.base_score.toFixed(1)}%</span>
              </div>
              <div className={styles.scoreBar}>
                <div className={styles.scoreLabel}>LLM Adjusted</div>
                <div className={styles.bar}>
                  <div className={styles.fill} style={{ width: `${signal.confidence_score}%` }} />
                </div>
                <span>{signal.confidence_score.toFixed(1)}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
