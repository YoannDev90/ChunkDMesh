use std::collections::HashMap;

#[derive(Debug, Clone)]
pub enum NbtValue {
    Byte(i8),
    Short(i16),
    Int(i32),
    Long(i64),
    Float(f32),
    Double(f64),
    ByteArray(Vec<u8>),
    String(String),
    List(Vec<NbtValue>),
    Compound(HashMap<String, NbtValue>),
    IntArray(Vec<i32>),
    LongArray(Vec<i64>),
    End,
}

pub struct NbtReader<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> NbtReader<'a> {
    pub fn new(data: &'a [u8]) -> Self {
        Self { data, pos: 0 }
    }

    fn read_exact(&mut self, n: usize) -> Option<&'a [u8]> {
        if self.pos + n > self.data.len() {
            return None;
        }
        let chunk = &self.data[self.pos..self.pos + n];
        self.pos += n;
        Some(chunk)
    }

    pub fn read_byte(&mut self) -> Option<i8> {
        let b = self.read_exact(1)?;
        Some(b[0] as i8)
    }

    pub fn read_short(&mut self) -> Option<i16> {
        let b = self.read_exact(2)?;
        Some(i16::from_be_bytes([b[0], b[1]]))
    }

    pub fn read_int(&mut self) -> Option<i32> {
        let b = self.read_exact(4)?;
        Some(i32::from_be_bytes([b[0], b[1], b[2], b[3]]))
    }

    pub fn read_long(&mut self) -> Option<i64> {
        let b = self.read_exact(8)?;
        Some(i64::from_be_bytes([
            b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
        ]))
    }

    fn read_float(&mut self) -> Option<f32> {
        let b = self.read_exact(4)?;
        Some(f32::from_be_bytes([b[0], b[1], b[2], b[3]]))
    }

    fn read_double(&mut self) -> Option<f64> {
        let b = self.read_exact(8)?;
        Some(f64::from_be_bytes([
            b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
        ]))
    }

    fn read_string(&mut self) -> Option<String> {
        let len = self.read_short()? as usize;
        let b = self.read_exact(len)?;
        String::from_utf8(b.to_vec()).ok()
    }

    pub fn read_payload(&mut self, tag_type: u8) -> Option<NbtValue> {
        match tag_type {
            0 => Some(NbtValue::End),
            1 => Some(NbtValue::Byte(self.read_byte()?)),
            2 => Some(NbtValue::Short(self.read_short()?)),
            3 => Some(NbtValue::Int(self.read_int()?)),
            4 => Some(NbtValue::Long(self.read_long()?)),
            5 => Some(NbtValue::Float(self.read_float()?)),
            6 => Some(NbtValue::Double(self.read_double()?)),
            7 => {
                let len = self.read_int()? as usize;
                let data = self.read_exact(len)?;
                Some(NbtValue::ByteArray(data.to_vec()))
            }
            8 => Some(NbtValue::String(self.read_string()?)),
            9 => self.read_list(),
            10 => self.read_compound(),
            11 => {
                let len = self.read_int()? as usize;
                let mut v = Vec::with_capacity(len);
                for _ in 0..len {
                    v.push(self.read_int()?);
                }
                Some(NbtValue::IntArray(v))
            }
            12 => {
                let len = self.read_int()? as usize;
                let mut v = Vec::with_capacity(len);
                for _ in 0..len {
                    v.push(self.read_long()?);
                }
                Some(NbtValue::LongArray(v))
            }
            _ => None,
        }
    }

    fn read_list(&mut self) -> Option<NbtValue> {
        let elem_type = self.read_byte()? as u8;
        let len = self.read_int()? as usize;
        let mut items = Vec::with_capacity(len);
        if elem_type == 0 {
            return Some(NbtValue::List(items));
        }
        for _ in 0..len {
            items.push(self.read_payload(elem_type)?);
        }
        Some(NbtValue::List(items))
    }

    fn read_compound(&mut self) -> Option<NbtValue> {
        let mut map = HashMap::new();
        loop {
            let tag_type = self.read_byte()? as u8;
            if tag_type == 0 {
                return Some(NbtValue::Compound(map));
            }
            let name = self.read_string()?;
            let value = self.read_payload(tag_type)?;
            map.insert(name, value);
        }
    }

    pub fn read_root(&mut self) -> Option<NbtValue> {
        let tag_type = self.read_byte()? as u8;
        let _name = self.read_string()?;
        self.read_payload(tag_type)
    }
}

// Helpers to extract typed values without full pattern matching
impl NbtValue {
    pub fn as_compound(&self) -> Option<&HashMap<String, NbtValue>> {
        match self {
            NbtValue::Compound(m) => Some(m),
            _ => None,
        }
    }

    pub fn as_list(&self) -> Option<&Vec<NbtValue>> {
        match self {
            NbtValue::List(l) => Some(l),
            _ => None,
        }
    }

    pub fn as_byte(&self) -> Option<i8> {
        match self {
            NbtValue::Byte(b) => Some(*b),
            _ => None,
        }
    }

    pub fn as_int(&self) -> Option<i32> {
        match self {
            NbtValue::Int(i) => Some(*i),
            _ => None,
        }
    }

    pub fn as_long(&self) -> Option<i64> {
        match self {
            NbtValue::Long(l) => Some(*l),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            NbtValue::String(s) => Some(s.as_str()),
            _ => None,
        }
    }

    pub fn as_long_array(&self) -> Option<&Vec<i64>> {
        match self {
            NbtValue::LongArray(a) => Some(a),
            _ => None,
        }
    }

    pub fn as_byte_array(&self) -> Option<&Vec<u8>> {
        match self {
            NbtValue::ByteArray(a) => Some(a),
            _ => None,
        }
    }
}
