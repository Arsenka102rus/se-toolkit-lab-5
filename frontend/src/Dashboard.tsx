import { useState, useEffect } from 'react';
import { Bar, Line } from 'react-chartjs-2';
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    BarElement,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend
} from 'chart.js';

// Регистрируем компоненты Chart.js
ChartJS.register(
    CategoryScale,
    LinearScale,
    BarElement,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend
);

interface ScoreBucket {
    bucket: string;
    count: number;
}

interface TimelinePoint {
    date: string;
    submissions: number;
}

interface PassRate {
    task: string;
    avg_score: number;
    attempts: number;
}

const getApiKey = (): string | null => {
    return localStorage.getItem('api_key');
};

async function fetchWithAuth<T>(url: string): Promise<T> {
    const apiKey = getApiKey();
    const response = await fetch(url, {
        headers: {
            'Authorization': `Bearer ${apiKey}`,
            'Content-Type': 'application/json',
        },
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
}

const Dashboard = () => {
    const [selectedLab, setSelectedLab] = useState('lab-04');
    const [scores, setScores] = useState<ScoreBucket[]>([]);
    const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
    const [passRates, setPassRates] = useState<PassRate[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const labs = ['lab-01', 'lab-02', 'lab-03', 'lab-04', 'lab-05'];

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            setError(null);

            const apiTarget = import.meta.env.VITE_API_TARGET || '';

            try {
                const [scoresData, timelineData, passRatesData] = await Promise.all([
                    fetchWithAuth<ScoreBucket[]>(`${apiTarget}/analytics/scores?lab=${selectedLab}`),
                    fetchWithAuth<TimelinePoint[]>(`${apiTarget}/analytics/timeline?lab=${selectedLab}`),
                    fetchWithAuth<PassRate[]>(`${apiTarget}/analytics/pass-rates?lab=${selectedLab}`)
                ]);

                setScores(scoresData);
                setTimeline(timelineData);
                setPassRates(passRatesData);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Unknown error');
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [selectedLab]);

    const barChartData = {
        labels: scores.map(item => item.bucket),
        datasets: [
            {
                label: 'Number of submissions',
                data: scores.map(item => item.count),
                backgroundColor: 'rgba(75, 192, 192, 0.6)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1,
            },
        ],
    };

    const lineChartData = {
        labels: timeline.map(item => item.date),
        datasets: [
            {
                label: 'Submissions per day',
                data: timeline.map(item => item.submissions),
                fill: false,
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.1,
            },
        ],
    };

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'top' as const,
            },
        },
    };

    if (loading) return <div>Loading...</div>;
    if (error) return <div>Error: {error}</div>;

    return (
        <div style={{ padding: '20px' }}>
            <h1>Analytics Dashboard</h1>

            <div style={{ marginBottom: '20px' }}>
                <label htmlFor="lab-select">Select Lab: </label>
                <select
                    id="lab-select"
                    value={selectedLab}
                    onChange={(e) => setSelectedLab(e.target.value)}
                    style={{ padding: '5px', marginLeft: '10px' }}
                >
                    {labs.map(lab => (
                        <option key={lab} value={lab}>{lab}</option>
                    ))}
                </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                <div style={{ height: '400px' }}>
                    <h2>Score Distribution</h2>
                    <Bar data={barChartData} options={chartOptions} />
                </div>

                <div style={{ height: '400px' }}>
                    <h2>Submissions Timeline</h2>
                    {timeline.length > 0 ? (
                        <Line data={lineChartData} options={chartOptions} />
                    ) : (
                        <p>No timeline data available</p>
                    )}
                </div>
            </div>

            <div style={{ marginTop: '40px' }}>
                <h2>Pass Rates by Task</h2>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ backgroundColor: '#f2f2f2' }}>
                            <th style={{ padding: '10px', textAlign: 'left' }}>Task</th>
                            <th style={{ padding: '10px', textAlign: 'left' }}>Average Score (%)</th>
                            <th style={{ padding: '10px', textAlign: 'left' }}>Attempts</th>
                        </tr>
                    </thead>
                    <tbody>
                        {passRates.map((item, index) => (
                            <tr key={index} style={{ borderBottom: '1px solid #ddd' }}>
                                <td style={{ padding: '10px' }}>{item.task}</td>
                                <td style={{ padding: '10px' }}>{item.avg_score.toFixed(1)}</td>
                                <td style={{ padding: '10px' }}>{item.attempts}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default Dashboard;