import { Card, Heading, Text, Flex } from '@radix-ui/themes';
import { useEffect, useState } from 'react';

const MetricsDashboard = () => {
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    const fetchMetrics = async () => {
      const res = await fetch('http://localhost:8000/metrics/json');
      const data = await res.json();
      setMetrics(data);
    };
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 15000); // auto-refresh every 15s
    return () => clearInterval(interval);
  }, []);

  return (
    <Flex direction="column" align="center" m="4">
      <Heading size="6" mb="3">Metrics Dashboard</Heading>
      {metrics ? (
        <Card style={{ padding: '1rem', width: '400px' }}>
          {Object.entries(metrics).map(([key, val]) => (
            <Text key={key}>
              <strong>{key}</strong>: {val}
            </Text>
          ))}
        </Card>
      ) : (
        <Text>Loading metrics...</Text>
      )}
    </Flex>
  );
};

export default MetricsDashboard;
