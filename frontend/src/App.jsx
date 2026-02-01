import { useEffect, useRef, useState } from 'react'
import { Container, Button, Card, Row, Modal, Col } from 'react-bootstrap'
import './App.css'
import 'bootstrap/dist/css/bootstrap.min.css'

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);

const [showModal, setShowModal] = useState(false);
const [selectedClaim, setSelectedClaim] = useState(null);

  const [transcriptSegments, setTranscriptSegments] = useState([]);

  const [claims, setClaims] = useState([]);

  const mediaRecorderReference = useRef(null);
  const audioContextReference = useRef(null);
  const analyserReference = useRef(null);
  const animationFrameReference = useRef(null);
  const wsRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    connectWebSocket();

    // Cleanup when component unmounts
    return () => {
      if (animationFrameReference.current) {
        cancelAnimationFrame(animationFrameReference.current);
      }

      if (wsRef.current) {
        wsRef.current.close();
      }
    }
  }, []);

  const connectWebSocket = () => {
    try {
      const ws = new WebSocket('ws://localhost:8000/ws');

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
        else if (data.type === 'processing_complete') {
          setIsProcessing(false);
          console.log("✅ Processing complete");
        }
      };

      ws.onerror = (error) => {
        console.error("WebSocket error: ", error);
        setWsConnected(false);
      };

      ws.onclose = () => {
        console.log("WebSocket disconnected.");
        setWsConnected(false);
        setTimeout(connectWebSocket, 3000);
      };

      wsRef.current = ws;
    } catch (error) {
      console.error("Failed to connect to WebSocket: ", error);
    }
  }

  const startRecording = async () => {
    if (!wsConnected) {
      alert("WebSocket not connected! Make sure the backend is running.");
      return;
    }

    // Clear previous transcript and claims
    setTranscriptSegments([]);
    setClaims([]);

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true
        }
      });

      // Setup audio visualisation
      audioContextReference.current = new AudioContext();
      analyserReference.current = audioContextReference.current.createAnalyser();
      const source = audioContextReference.current.createMediaStreamSource(stream);
      source.connect(analyserReference.current);
      analyserReference.current.fftSize = 2048;
      analyserReference.current.smoothingTimeConstant = 0.3;
      visualiseAudio();

      // Create MediaRecorder with WebM format
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
        audioBitsPerSecond: 16000
      });

      const sessionId = `${Date.now()}-${Math.random()}`;
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'start_recording',
          id: sessionId
        }));
        console.log(`🎤 Sent session ID: `, sessionId);
      }

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(event.data);
          console.log(`📤 Sent audio chunk: ${event.data.size} bytes`);
        }
      };

      mediaRecorder.start(250);
      mediaRecorderReference.current = mediaRecorder;
      setIsRecording(true);

      console.log("🎤 Recording started; audio format: ", mediaRecorder.mimeType);
    } catch (error) {
      console.error("❌ Error accessing microphone: ", error);
      alert("Could not access microphone, please check permissions.");
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!wsConnected) {
      alert("WebSocket not connected! Make sure the backend is running.");
      return;
    }

    // Check if it's an audio file
    if (!file.type.startsWith('audio/')) {
      alert("Please upload an audio file.");
      return;
    }

    setIsProcessing(true);
    setTranscriptSegments([]);
    setClaims([]);

    try {
      // Send session ID
      const sessionId = `${Date.now()}-${Math.random()}`;
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'upload_file',
          id: sessionId
        }));
        console.log(`📤 Sent session ID: `, sessionId);
      }

      // Read and send file in chunks
      const chunkSize = 8192; // 8KB chunks
      let offset = 0;

      while (offset < file.size) {
        const chunk = file.slice(offset, offset + chunkSize);
        const arrayBuffer = await chunk.arrayBuffer();
        
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(arrayBuffer);
          console.log(`📤 Sent audio chunk: ${arrayBuffer.byteLength} bytes (${offset + arrayBuffer.byteLength}/${file.size})`);
        }
        
        offset += chunkSize;
        
        // Small delay to avoid overwhelming the connection
        await new Promise(resolve => setTimeout(resolve, 50));
      }

      console.log(`✅ Finished sending file: ${file.name}`);
      setIsProcessing(false);
    } catch (error) {
      console.error("❌ Error uploading file: ", error);
      alert("Error processing audio file.");
      setIsProcessing(false);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderReference.current && mediaRecorderReference.current.state !== 'inactive') {
      mediaRecorderReference.current.stop();
      mediaRecorderReference.current.stream.getTracks().forEach(track => track.stop());
      setIsRecording(false);
      setAudioLevel(0);
      setIsProcessing(true);

      if (animationFrameReference.current) {
        cancelAnimationFrame(animationFrameReference.current);
      }

      // Send stop recording message to backend
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'stop_recording'
        }));
        console.log("🛑 Sent stop recording signal");
      }

      console.log("🛑 Recording stopped");
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
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept="audio/*"
              style={{ display: 'none' }}
            />
            <Button
              variant={isRecording ? 'danger' : 'success'}
              size='lg'
              onClick={isRecording ? stopRecording : startRecording}
              disabled={!wsConnected || isProcessing}
              style={{ minWidth: '200px', marginRight: '10px' }}>
                {isRecording ? '🛑 Stop Recording' : '🎤 Start Recording'}
            </Button>
            <Button
              variant='primary'
              size='lg'
              onClick={() => fileInputRef.current?.click()}
              disabled={!wsConnected || isProcessing || isRecording}
              style={{ minWidth: '200px' }}>
                {isProcessing ? 'Processing...' : '📁 Upload Audio File'}
            </Button>
            {!wsConnected && (
              <small className='text-danger d-block mt-2'>
                Backend not connected!
              </small>
            )}
            {isRecording && (
              <small className='text-info d-block mt-2'>
                🎤 Recording in progress...
              </small>
            )}
            {isProcessing && (
              <small className='text-info d-block mt-2'>
                ⏳ Processing audio...
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