import { useEffect, useRef, useState } from 'react'
import { Container, Button, Card, Row, Modal, Col } from 'react-bootstrap'
import './App.css'
import 'bootstrap/dist/css/bootstrap.min.css'

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);

const [showModal, setShowModal] = useState(false);
const [selectedClaim, setSelectedClaim] = useState(null);

  const [transcriptSegments, setTranscriptSegments] = useState([]);

  const [claims, setClaims] = useState([]);

  const mediaRecorderReference = useRef(null);
  const audioContextReference = useRef(null);
  const analyserReference = useRef(null);
  const sourceNodeRef = useRef(null);
  const processorNodeRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const animationFrameReference = useRef(null);
  const wsRef = useRef(null);
  // Guard and reconnection controls
  const reconnectTimerRef = useRef(null);
  const shouldReconnectRef = useRef(true);

  useEffect(() => {
    // allow reconnects while mounted
    shouldReconnectRef.current = true;
    connectWebSocket();

    // Cleanup when component unmounts
    return () => {
      // prevent auto-reconnects after unmount
      shouldReconnectRef.current = false;

      // clear any pending reconnect timer
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      if (animationFrameReference.current) {
        cancelAnimationFrame(animationFrameReference.current);
      }

      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    }
  }, []);

  const connectWebSocket = () => {
    try {
      // Guard: avoid opening a second socket if one is open or connecting
      if (wsRef.current && [WebSocket.OPEN, WebSocket.CONNECTING].includes(wsRef.current.readyState)) {
        console.log("WebSocket is already open or connecting. Skipping new connection.");
        return;
      }

      const ws = new WebSocket('ws://localhost:8000/ws');
      // Assign immediately to avoid race conditions with onclose/onerror
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("WebSocket connected!");
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log("Received from backend: ", data);

        if (data.type === 'transcript') {
          setTranscriptSegments(prev => [...prev, {
               id: `seg-${Date.now()}-${Math.random()}`,
               text: data.text,
               claimId: null
         }]);
        } else if (data.type === 'claim_detected') {
            const claimId = data.id;
            const claimText = data.claim;

            // Find the last segment that contains this claim
            setTranscriptSegments(prev => {
                for (let i = prev.length - 1; i >= 0; i--) {
                    const segment = prev[i];
                    const claimIndex = segment.text.indexOf(claimText);

                    if (claimIndex !== -1 && !segment.claimId) {
                        const before = segment.text.substring(0, claimIndex);
                        const after = segment.text.substring(claimIndex + claimText.length);

                        const newSegments = [...prev.slice(0, i)];

                        // Add before text if it exists
                        if (before) {
                            newSegments.push({
                                id: `seg-${Date.now()}-before`,
                                text: before,
                                claimId: null
                            });
                        }

                        // Add the claim itself
                        newSegments.push({
                            id: `seg-${Date.now()}-claim`,
                            text: claimText,
                            claimId: claimId
                        });

                        // Add the after text if it exists
                        if (after) {
                            newSegments.push({
                                id: `seg-${Date.now()}-after`,
                                text: after,
                                claimId: null
                            });
                        }

                        // Add any segments that came after
                        newSegments.push(...prev.slice(i + 1));

                        return newSegments;
                    }
                }

                // If claim not found in existing segments, log warning
                console.log("Claim not found in transcript: ", claimText);
                return prev;
             });

          setClaims(prev => [...prev, {
            id: claimId,
            text: data.claim,
            status: 'checking',
            isTrue: null,
            explanation: null
          }]);
        }

        else if (data.type === 'fact_check') {
          setClaims(prev => prev.map(c =>
            c.id === data.id
            ? { ...c,
                status: 'complete',
                isTrue: data.result.isTrue,
                 explanation: data.result.explanation
                 }
            : c
          ));
        }
      };

      ws.onerror = (error) => {
        console.error("WebSocket error: ", error);
        setWsConnected(false);
      };

      ws.onclose = () => {
        console.log("WebSocket disconnected.");
        setWsConnected(false);
        // Auto-reconnect with guard to avoid duplicates
        if (!shouldReconnectRef.current) {
          return;
        }

        // If there's already an open/connecting socket, don't schedule another
        if (wsRef.current && [WebSocket.OPEN, WebSocket.CONNECTING].includes(wsRef.current.readyState)) {
          return;
        }

        // Ensure only one reconnect timer is pending
        if (reconnectTimerRef.current) {
          clearTimeout(reconnectTimerRef.current);
        }

        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connectWebSocket();
        }, 3000);
      };

    } catch (error) {
      console.error("Failed to connect to WebSocket: ", error);
    }
  }

  // Helpers for PCM streaming (16kHz mono Linear16)
  const downsampleBuffer = (buffer, inputSampleRate, outSampleRate) => {
    if (outSampleRate === inputSampleRate) {
      return buffer;
    }
    const sampleRateRatio = inputSampleRate / outSampleRate;
    const newLength = Math.round(buffer.length / sampleRateRatio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
      let accum = 0, count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i];
        count++;
      }
      result[offsetResult] = count > 0 ? accum / count : 0;
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
    return result;
  };

  const floatTo16BitPCM = (float32Array) => {
    const len = float32Array.length;
    const result = new Int16Array(len);
    for (let i = 0; i < len; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      result[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return result.buffer;
  };

  const startRecording = async () => {
    if (!wsConnected) {
      alert("WebSocket not connected! Make sure the backend is running.");
      return;
    }

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 48000,
          echoCancellation: true,
          noiseSuppression: true
        }
      });

      mediaStreamRef.current = stream;
      // Setup WebAudio graph
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      audioContextReference.current = new AudioCtx();
      const ac = audioContextReference.current;

      // Visualizer
      analyserReference.current = ac.createAnalyser();
      analyserReference.current.fftSize = 2048;
      analyserReference.current.smoothingTimeConstant = 0.3;

      // Source from mic
      sourceNodeRef.current = ac.createMediaStreamSource(stream);
      sourceNodeRef.current.connect(analyserReference.current);

      // Processor to capture PCM frames
      processorNodeRef.current = ac.createScriptProcessor(4096, 1, 1);
      processorNodeRef.current.onaudioprocess = (event) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        const input = event.inputBuffer.getChannelData(0);
        // Downsample to 16kHz mono
        const downsampled = downsampleBuffer(input, ac.sampleRate, 16000);
        const pcm16 = floatTo16BitPCM(downsampled);
        wsRef.current.send(pcm16);
      };

      // Important: connect to destination so processor runs; output is silence
      sourceNodeRef.current.connect(processorNodeRef.current);
      processorNodeRef.current.connect(ac.destination);

      visualiseAudio();
      setIsRecording(true);

      console.log("Recording started; streaming PCM16 @16kHz over WebSocket. Input sampleRate=", audioContextReference.current.sampleRate);
    } catch (error) {
    console.error("Error accessing microphone: ", error);
    alert("Could not access microphone, please check permissions.");
    }
  };

  const stopRecording = () => {
    try {
      if (processorNodeRef.current) {
        processorNodeRef.current.disconnect();
        processorNodeRef.current.onaudioprocess = null;
        processorNodeRef.current = null;
      }
      if (sourceNodeRef.current) {
        sourceNodeRef.current.disconnect();
        sourceNodeRef.current = null;
      }
      if (analyserReference.current) {
        // no explicit disconnect needed if source disconnected
      }
      if (audioContextReference.current) {
        // Safari may not support close; wrap in try
        try { audioContextReference.current.close(); } catch (e) {}
        audioContextReference.current = null;
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(t => t.stop());
        mediaStreamRef.current = null;
      }

      setIsRecording(false);
      setAudioLevel(0);
      if (animationFrameReference.current) {
        cancelAnimationFrame(animationFrameReference.current);
        animationFrameReference.current = null;
      }
      console.log("Recording stopped");
    } catch (e) {
      console.error("Error while stopping recording", e);
    }
  };

  const renderTranscript = () => {
    return transcriptSegments.map((segment) => {
      if (!segment.claimId) {
        return <span key={segment.id}>{segment.text}</span>;
      }

      const claim = claims.find(c => c.id === segment.claimId);
      let colour = '#000000';

      if (claim) {
        if (claim.status === 'checking') {
          colour = '#6c757d';
        } else if (claim.status === 'complete') {
          colour = claim.isTrue ? '#10b981' : '#dc3545';
        }
      }

      return (
        <span
          key={segment.id}
          style={{
            color: colour,
            fontWeight: '500',
            cursor: claim?.status === 'complete' ? 'pointer' : 'default'
          }}
          onClick={() => claim?.status === 'complete' && handleClaimClick(claim)}>
            {segment.text}
        </span>
      );
    });
  };

  const handleClaimClick = (claim) => {
    if (claim.status === 'complete') {
      setSelectedClaim(claim);
      setShowModal(true);
    }
  };

  const visualiseAudio = () => {
    if (!analyserReference.current) return;

    const dataArray = new Uint8Array(analyserReference.current.fftSize);

    const updateLevel = () => {
      analyserReference.current.getByteTimeDomainData(dataArray);

      let sum = 0;
      for(let i = 0; i < dataArray.length; i++) {
        const normalised = (dataArray[i] - 128) / 128;
        sum += normalised * normalised;
      }

      const rms = Math.sqrt(sum / dataArray.length);
      const level = rms * 300;

      setAudioLevel(Math.min(100, level));
      animationFrameReference.current = requestAnimationFrame(updateLevel);
    };

    updateLevel();
  };

  return (
    <Container fluid style={{ height: '100vh', padding: '20px' }}>
      <Row style={{ height: '100%' }}>
        {/* Left-side - main content */}
        <Col md={8} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <h1 className='mb-4'>
            TruthStream
          </h1>

          <div className='mb-4'>
            <Button
              variant={isRecording ? 'danger' : 'primary'}
              size='lg'
              onClick={isRecording ? stopRecording : startRecording}
              disabled={!wsConnected}
              style={{ minWidth: '200px' }}>
                {isRecording ? 'Stop Recording' : 'Start Recording'}
            </Button>
            {!wsConnected && (
              <small className='text-danger d-block mt-2'>
                Backend not connected!
              </small>
            )}
          </div>

          {/* Live transcript */}
          <Card style={{ flex: 1, overflow: 'hidden', border: 'none', backgroundColor: 'rgba(0, 0, 0, 256)' }}>
            <Card.Body style={{ height: '100%', overflow: 'auto' }}>
              <h2 className='mb-3'>
                Live Transcript
              </h2>
              <div style={{ fontSize: '1.1rem', lineHeight: 1.8 }}>
                <p>{renderTranscript()}</p>
              </div>
            </Card.Body>
          </Card>
        </Col>

        {/* Right side - Claims sidebar */}
        <Col md={4} style={{
          height: '100%',
          paddingLeft: '20px'
        }}>
          <Card style={{ height: '100%', border: 'none', backgroundColor: 'rgba(0, 0, 0, 256)' }}>
            <Card.Body style={{ height: '100%', overflow: 'auto' }}>
              <h3 className='mb-4'>
                Claims
              </h3>

              {claims.length === 0 ? (
                <p className='text-muted'>
                  No claims detected yet
                </p>
              ) : (
                <div>
                  {claims.map((claim) => (
                    <div
                      className='bounce-in'
                      key={claim.id}
                      onClick={() => handleClaimClick(claim)}
                      style={{
                        padding: '15px',
                        marginBottom: '15px',
                        borderRadius: '8px',
                        backgroundColor: 'rgba(0, 0, 0, 256)',
                        border: '1px solid #dee2e6',
                        cursor: claim.status === 'complete' ? 'pointer' : 'default',
                        transition: 'all 0.2s'
                      }}
                      onMouseEnter={(e) => {
                        if (claim.status === 'complete') {
                          e.currentTarget.style.transform = 'translateY(-2px)';
                          e.currentTarget.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.1)'
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = 'none';
                      }}>
                        <p style={{
                          margin: 0,
                          color: claim.status === 'checking'
                          ? '#6c757d'
                          : (claim.isTrue ? '#10b981' : '#dc3545'),
                          fontWeight: '500',
                          fontSize: '0.95rem'
                        }}>
                          {claim.text}
                        </p>
                        {claim.status === 'checking' && (
                          <small className='d-block mt-2'>
                            ⏳ Checking...
                          </small>
                        )}
                    </div>
                  ))}
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Modal for claim explanation */}
      <Modal show={showModal} onHide={() => setShowModal(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>
            Claim Details
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selectedClaim && (
            <>
              <p style={{
                color: selectedClaim.isTrue ? '#10b981' : '#dc3545',
                fontWeight: '600',
                fontSize: '1.1rem',
                marginBottom: '15px'
              }}>
                {selectedClaim.text}
              </p>
              <p style={{
                fontStyle: 'italic',
                color: '#6c757d',
                lineHeight: '1.6'
              }}>
                {selectedClaim.explanation}
              </p>
            </>
          )}
        </Modal.Body>
      </Modal>
    </Container>
  )
}

export default App