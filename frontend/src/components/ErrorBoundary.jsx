import { Component } from 'react';
import { Link } from 'react-router-dom';
import { Banner } from './ui';

/** Catches unexpected rendering errors so a screen never goes blank. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prev) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  componentDidCatch(error, info) {
    console.error('PitPulse screen error:', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Banner tone="error" title="This screen could not be displayed">
        <ul>
          <li>An unexpected problem occurred while drawing this view ({String(this.state.error.message || this.state.error)}).</li>
          <li><b>Still available:</b> the other analysis screens and your loaded session.</li>
          <li><b>Next step:</b> <Link to="/overview">return to the Overview</Link> or <Link to="/">reload the session</Link>.</li>
        </ul>
      </Banner>
    );
  }
}
