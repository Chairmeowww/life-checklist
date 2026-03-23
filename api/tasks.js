import { createClient } from '@supabase/supabase-js';
import { createHash } from 'crypto';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

function hashPin(pin) {
  return createHash('sha256').update(pin.trim()).digest('hex');
}

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Pin');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const pin = req.headers['x-pin'];
  if (!pin) return res.status(401).json({ error: 'PIN required' });

  const pinHash = hashPin(pin);

  if (req.method === 'GET') {
    const { data, error } = await supabase
      .from('user_data')
      .select('data')
      .eq('pin_hash', pinHash)
      .single();

    if (error || !data) {
      return res.status(404).json({ error: 'No data found for this PIN' });
    }
    return res.status(200).json(data.data);
  }

  if (req.method === 'POST') {
    const body = req.body;

    // Upsert: create if new PIN, update if existing
    const { error } = await supabase
      .from('user_data')
      .upsert(
        { pin_hash: pinHash, data: body, updated_at: new Date().toISOString() },
        { onConflict: 'pin_hash' }
      );

    if (error) {
      return res.status(500).json({ error: error.message });
    }
    return res.status(200).json({ ok: true });
  }

  return res.status(405).json({ error: 'Method not allowed' });
}
